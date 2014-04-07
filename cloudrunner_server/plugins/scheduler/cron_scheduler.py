#!/usr/bin/python
# -*- coding: utf-8 -*-
# vim: tabstop=4 shiftwidth=4 softtabstop=4

# /*******************************************************
#  * Copyright (C) 2013-2014 CloudRunner.io <info@cloudrunner.io>
#  *
#  * Proprietary and confidential
#  * This file is part of CloudRunner Server.
#  *
#  * CloudRunner Server can not be copied and/or distributed without the express
#  * permission of CloudRunner.io
#  *******************************************************/

from crontab import CronTab
from crontab import __version__

if __version__ < '1.7':
    raise Exception("Scheduler plugin requires python-crontab >= 1.7")

import logging
import os
import sys
import tempfile
import uuid
import pwd

from cloudrunner import LIB_DIR
from cloudrunner_server.plugins.args_provider import CliArgsProvider

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
        keys = ('user', 'token', 'id', 'name', 'file', '_')
        values = self.meta.split(SEPARATOR)

        params = dict(zip(keys, values))
        for k, v in params.items():
            setattr(self, k, v)

    @property
    def period(self):
        return str(self.cron_job.slices)

    @staticmethod
    def _prepare_job_meta(user, token, job_id, name, task_file):
        params = dict(user=user, token=token, job_id=job_id,
                      name=name, file=task_file)
        comment = SEPARATOR.join([user, token, job_id, name, task_file, ''])
        return comment


def _default_dir():
    _def_dir = os.path.join(LIB_DIR, "cloudrunner", "plugins", "scheduler")
    if not os.path.exists(_def_dir):
        os.makedirs(_def_dir)
    return _def_dir


class CronScheduler(CliArgsProvider):

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
            job_id = str(uuid.uuid4())
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
                period = [str(term) for term in period]
                cron.setall(*period)
            except:
                return (False, 'Period is not valid: %s' % period)

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
                job.cron_job.setall(*period)
                self.crontab.write()
            return (True, "Updated")

        return (False, 'Not found')

    def view(self, user, name, **kwargs):
        crons = self._own(user)
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

    def list(self, where=None, *args, **kwargs):
        jobs = []
        search = {}
        if 'search_pattern' in kwargs:
            search['meta'] = kwargs['search_pattern']
        if not where:
            where = self._all
        for job in where(**search):
            jobs.append(dict(name=job.name,
                             user=job.user,
                             enabled=job.enabled,
                             period=job.time))

        return (True, jobs)

    def delete(self, user, name=None, **kwargs):
        crons = self._own(user)
        for job in crons:
            print job.user, user, job.name, name
            if job.user == user and job.name == name:
                self.crontab.remove(job.cron_job)
                self.crontab.write()
                os.unlink(job.file)
                return (True, 'Cron job %s removed' % name)

        return (False, 'Cron not found')

    def append_cli_args(self, arg_parser):
        sched_actions = arg_parser.add_subparsers(dest='action')

        _list = sched_actions.add_parser('list', add_help=False,
                                         help='List all scheduled tasks')
        _list.add_argument('--json', action="store_true", help='JSON output')

        add = sched_actions.add_parser('add', add_help=False,
                                       help='Create scheduled task')
        add.add_argument('name', help='Job name')
        add.add_argument('content', help='Content')
        add.add_argument('period', nargs="+",
                         help='Execution period, in cron format e.g. '
                         '*/5 * * * *')

        edit = sched_actions.add_parser('edit', add_help=False,
                                        help='Edit scheduled task')
        edit.add_argument('name', help='Job name')
        edit.add_argument('content', help='Content')
        edit.add_argument('period', nargs="+",
                          help='Execution period, in cron format e.g. '
                          '*/5 * * * *')

        show = sched_actions.add_parser('show', add_help=False,
                                        help='Get scheduled task contents')
        show.add_argument('name', help='Job name')
        delete = sched_actions.add_parser('delete', add_help=False,
                                          help='Delete scheduled task')
        delete.add_argument('name', help='Job name')
        return "scheduler"

    def call(self, user_org, data, ctx, args):
        if args.action == "list":
            success, jobs = self.list(where=lambda *args:
                                      self._own(user_org[0]))
            if args.json:
                return success, jobs
            rows = []
            if success:
                rows.append('%-20s %-20s %-20s' %
                           ('Name', 'Period', 'Enabled'))
                for job in jobs:
                    rows.append('%(name)-20s %(period)-20s %(enabled)-20s' %
                                job)
            else:
                return False, jobs

            return True, '\n'.join(rows)
        elif args.action == "add":
            bin_path = os.path.dirname(os.path.abspath(sys.argv[0]))
            kwargs = {}
            kwargs["exec"] = os.path.join(bin_path, 'cloudrunner-master')
            ret = self.add(user_org[0], data, args.name,
                           args.period,
                           ctx.create_auth_token(expiry=-1),
                           **kwargs)
            return ret
        elif args.action == "edit":
            bin_path = os.path.dirname(os.path.abspath(sys.argv[0]))
            kwargs = {}
            ret = self.edit(user_org[0], data, args.name,
                            args.period,
                            **kwargs)
            return ret
        elif args.action == "show":
            return self.show(user_org[0], args.name)
        elif args.action == "delete":
            return self.delete(user_org[0], args.name)
