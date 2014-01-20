#!/usr/bin/python
# -*- coding: utf-8 -*-
# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2013 CloudRunner.IO
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from crontab import CronTab
import logging
import os
import sys
import tempfile
import uuid
import pwd

from cloudrunner import VAR_DIR

SEPARATOR = '\t'
LOG = logging.getLogger("CronScheduler")


class Job(object):

    def __init__(self, cron_job):
        self.meta = cron_job.meta()
        self.enabled = cron_job.enabled
        self.command = cron_job.command.command()
        self.time = cron_job.render_time()
        self.cron_job = cron_job

        self._append_job_params()

    def _append_job_params(self):
        keys = ('user', 'token', 'id', 'name', 'file', '_')
        values = self.meta.split(SEPARATOR)

        params = dict(zip(keys, values))
        for k, v in params.items():
            setattr(self, k, v)

    @property
    def period(self):
        return self.cron_job.render_time()

    @staticmethod
    def _prepare_job_meta(user, token, job_id, name, task_file):
        params = dict(user=user, token=token, job_id=job_id,
                      name=name, file=task_file)
        comment = SEPARATOR.join([user, token, job_id, name, task_file, ''])
        return comment


def _default_dir():
    _def_dir = os.path.join(VAR_DIR, "cloudrunner", "plugins", "scheduler")
    if not os.path.exists(_def_dir):
        os.makedirs(_def_dir)
    return _def_dir


class CronScheduler(object):

    def __init__(self):
        if os.geteuid() == 0:
            # Root/system cron
            self.crontab = CronTab()
        else:
            self.crontab = CronTab(user=pwd.getpwuid(os.getuid())[0])
        self.job_dir = getattr(CronScheduler, 'job_dir', _default_dir())
        if not os.path.exists(self.job_dir):
            os.makedirs(self.job_dir)

    def _own(self, user):
        jobs = []
        user_pattern = "%s%s" % (user, SEPARATOR)
        for cron_job in self.crontab:
            job = Job(cron_job)
            if job.meta.startswith(user_pattern):
                jobs.append(job)

        return jobs

    def _all(self, **filters):
        jobs = []
        for cron_job in self.crontab:
            job = Job(cron_job)
            if filters:
                for k, v in filters.items():
                    if hasattr(job, k) and getattr(job, k, None) == v:
                        jobs.append(job)
            else:
                jobs.append(job)

        return jobs

    def add(self, user, payload=None, name=None,
            period=None, auth_token=None, **kwargs):
        try:
            job_id = str(uuid.uuid1())
            kwargs['job_id'] = job_id
            name = name.replace(SEPARATOR, '_')
            if self._all(name=name):
                return (False, "Job with the name %s exists" % name)

            command = '%(exec)s schedule run %(job_id)s' % kwargs

            def create_payload():
                return tempfile.mkstemp(dir=self.job_dir,
                                        prefix='cloudr_',
                                        suffix='_job',
                                        text=True)
            try:
                (_file_fd, task_file) = create_payload()
            except OSError:
                (_file_fd, task_file) = os.makedirs(self.job_dir)
                create_payload()
            os.write(_file_fd, payload)
            os.close(_file_fd)

            comment = Job._prepare_job_meta(user, auth_token, job_id,
                                            name, task_file)

            cron = self.crontab.new(command=command, comment=comment)
            try:
                cron.set_slices(period.split(' '))
            except:
                return (False, 'Period is not valid')

            if not cron.is_valid():
                return (False, 'Cron is not valid')

            cron.enable()
            self.crontab.write()

            return (True, None)
        except Exception, ex:
            LOG.exception(ex)
            return (False, '%r' % ex)

    def get(self, job_id):
        for cron_job in self.crontab:
            job = Job(cron_job)
            if job.id == job_id:
                return job

    def edit(self, user, payload=None, name=None,
             period=None, **kwargs):
        crons = self._all()
        if not name:
            return (False, 'Not found')
        name = name.replace(SEPARATOR, '_')
        job = self._all(name=name)
        if job:
            job = job[0]
            if payload:
                open(job.file, 'w').write(payload)
            if period and job.period != period:
                job.cron_job.set_slices(period.split(' '))
                self.crontab.write()
            return (True, "Updated")

        return (False, 'Not found')

    def view(self, user, name, **kwargs):
        crons = self._all(name=name)
        for job in crons:
            try:
                content = open(job.file).read()
            except:
                content = "#Error: Cannot open file!"
            return (True, dict(job_id=job.id, name=name,
                               content=content,
                               owner=job.user,
                               period=job.period))

        return (False, 'Not found')

    show = view  # Alias

    def list(self, *args, **kwargs):
        jobs = []
        search = {}
        if 'search_pattern' in kwargs:
            search['meta'] = kwargs['search_pattern']
        for job in self._all(**search):
            jobs.append(dict(name=job.name,
                             user=job.user,
                             enabled=job.enabled,
                             period=job.time))

        return (True, jobs)

    def delete(self, user, name=None, **kwargs):
        crons = self._own(user)
        for job in crons:
            if job.user == user and job.name == name:
                self.crontab.remove(job.cron_job)
                self.crontab.write()
                os.unlink(job.file)
                return (True, 'Cron job %s removed' % name)

        return (False, 'Cron not found')
