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

from cloudrunner_server.plugins.scheduler import Period

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
    def _prepare_job_meta(user, name, *args):
        comment = SEPARATOR.join([user, name] + list(args))
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
                if all([getattr(job, k, None) == v
                        for k, v in filters.items() if hasattr(job, k)]):
                    jobs.append(job)
            else:
                jobs.append(job)

        return jobs

    def add(self, user, name, period, url, *args):
        assert isinstance(period, Period)
        try:
            _cron = self.crontab()
            name = name.replace(SEPARATOR, '_')
            if self._jobs(user=user, name=name):
                return (False, "Job with the name %s exists" % name)

            comment = Job._prepare_job_meta(user, name, *args)
            url = url.replace('&', '\&').replace('$', '\$').replace('%', '\%')
            url = url.replace('"', '\"')
            cmd = '%s >/dev/null 2>&1' % url

            cron = _cron.new(command=cmd, comment=comment)
            try:
                cron.setall(*period.values())
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

    def edit(self, user, name, period, *args):
        assert isinstance(period, Period)
        name = name.replace(SEPARATOR, '_')
        _cron = self.crontab()
        jobs = self._jobs(user=user, name=name, cron=_cron)
        if not jobs:
            return (False, 'Job %s not found' % name)
        job = jobs[0]
        try:
            job.cron_job.comment = Job._prepare_job_meta(user, name, *args)
            if period and job.period != period._:
                job.cron_job.setall(*period.values())
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
