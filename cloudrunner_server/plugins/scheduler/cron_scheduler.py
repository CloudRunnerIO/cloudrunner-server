#!/usr/bin/python
# -*- coding: utf-8 -*-
# vim: tabstop=4 shiftwidth=4 softtabstop=4

# /*******************************************************
#  * Copyright (C) 2013-2014 CloudRunner.io <info@cloudrunner.io>
#  *
#  * Proprietary and confidential
#  * This file is part of CloudRunner Server.
#  *
#  * CloudRunner Server can not be copied and/or distributed
#  * without the express permission of CloudRunner.io
#  *******************************************************/

from crontab import CronTab
from crontab import __version__

if __version__ < '1.7':
    raise Exception("Scheduler plugin requires python-crontab >= 1.7")

import logging
import os
import pwd

SEPARATOR = '\t'
LOG = logging.getLogger("CronScheduler")


class Job(object):

    def __init__(self, cron_job):
        self.meta = cron_job.comment
        self.enabled = cron_job.enabled
        self.command = cron_job.command
        self.time = str(cron_job.slices)
        self.cron_job = cron_job

        self._append_job_params()

    def _append_job_params(self):
        keys = ('user', 'name')
        values = self.meta.split(SEPARATOR)

        params = dict(zip(keys, values))
        for k, v in params.items():
            setattr(self, k, v)

    @property
    def period(self):
        return str(self.cron_job.slices)

    @staticmethod
    def _prepare_job_meta(user, name):
        comment = SEPARATOR.join([user, name])
        return comment


class CronScheduler(object):

    def __init__(self):
        self.uid = pwd.getpwuid(os.getuid())[0]

    def crontab(self):
        crontab = CronTab(user=self.uid)
        return crontab

    def _jobs(self, cron=None, **filters):
        jobs = []
        _cron = cron or self.crontab()
        for cron_job in _cron:
            job = Job(cron_job)
            if filters:
                for k, v in filters.items():
                    if hasattr(job, k) and getattr(job, k, None) == v:
                        jobs.append(job)
            else:
                jobs.append(job)

        return jobs

    def add(self, user, name, period, auth_token, **kwargs):
        try:
            _cron = self.crontab()
            name = name.replace(SEPARATOR, '_')
            if self._jobs(user=user, name=name):
                return (False, "Job with the name %s exists" % name)

            comment = Job._prepare_job_meta(user, name)
            cmd = kwargs.get("exec", "# CR Job scheduler: exec not passed")
            cmd = 'curl %s' % cmd.replace('&', '\&').replace('$', '\$')

            cron = _cron.new(command=cmd, comment=comment)
            try:
                if not isinstance(period, list):
                    period = period.split(' ')
                cron.setall(*period)
            except:
                return (False, 'Period is not valid: %s' % period)

            if not cron.is_valid():
                return (False, 'Cron is not valid')
            cron.enable()
            _cron.write()

            return (True, None)
        except Exception, ex:
            LOG.exception(ex)
            return (False, '%r' % ex)

    def get(self, user, name):
        jobs = self._jobs(user=user, name=name)
        if jobs:
            return jobs[0]

    def edit(self, user, name, period):
        name = name.replace(SEPARATOR, '_')
        _cron = self.crontab()
        jobs = self._jobs(user=user, name=name, cron=_cron)
        if not jobs:
            return (False, 'Job %s not found' % name)
        job = jobs[0]
        try:
            if not isinstance(period, list):
                period = period.split(' ')
            if period and job.period != period:
                job.cron_job.setall(*period)
                _cron.write()
            return (True, "Updated")

        except Exception, ex:
            LOG.exception(ex)
            return (False, 'Update failed')

    def delete(self, user, name):
        _cron = self.crontab()
        jobs = self._jobs(user=user, name=name, cron=_cron)
        if not jobs:
            return (False, 'Job %s not found' % name)
        job = jobs[0]
        try:
            _cron.remove(job.cron_job)
            _cron.write()
            return (True, 'Job %s removed' % name)
        except Exception, ex:
            LOG.exception(ex)
            return (False, 'Job not found')
