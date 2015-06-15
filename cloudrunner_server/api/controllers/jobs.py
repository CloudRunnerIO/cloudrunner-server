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

import json
import logging
import os
from pecan import conf, expose, request
from pecan.hooks import HookController
from sqlalchemy.orm import exc

from cloudrunner_server.api.decorators import wrap_command
from cloudrunner_server.api.hooks.error_hook import ErrorHook
from cloudrunner_server.api.hooks.db_hook import DbHook
from cloudrunner_server.api.hooks.perm_hook import PermHook
from cloudrunner_server.api.model import (Job, Deployment, User)
from cloudrunner_server.api.util import JsonOutput as O
from cloudrunner_server.plugins.scheduler import Period

schedule_manager = conf.schedule_manager

JOB_FIELDS = ('name', 'target', 'arguments', 'enabled', 'private')
LOG = logging.getLogger()
EXE_PATH = os.popen('which cloudrunner-trigger').read().strip()
if not EXE_PATH:
    LOG.warn("Scheduler job executable not found on server")
else:
    EXE_PATH = "%s exec %%s" % EXE_PATH


def _try_load(s):
    try:
        return json.loads(s)
    except:
        return s


class Jobs(HookController):

    __hooks__ = [ErrorHook(), DbHook(),
                 PermHook(dont_have=set(['is_super_admin']))]

    @expose('json', generic=True)
    @wrap_command(Job, model_name="Job")
    def jobs(self, *args, **kwargs):
        if not args:
            jobs = []
            query = Job.visible(request)
            jobs = [t.serialize(
                skip=['id', 'key', 'owner_id', 'deployment_id', 'uid'],
                rel=[('owner.username', 'owner'),
                     ('params', 'params', _try_load),
                     ('deployment', 'deployment', lambda d: d.name)])
                    for t in query.all()]
            return O._anon(jobs=sorted(jobs, key=lambda t: t['name'].lower()),
                           quota=dict(allowed=request.user.tier.cron_jobs))
        else:
            job_name = args[0]
            try:
                job = Job.visible(request).filter(Job.name == job_name).one()
                return O.job(**job.serialize(
                    skip=['id', 'key', 'owner_id', 'deployment_id', 'uid'],
                    rel=[('owner.username', 'owner'),
                         ('params', 'params', _try_load),
                         ('deployment', 'deployment', lambda d: d.name)]))
            except exc.NoResultFound, ex:
                LOG.error(ex)
                request.db.rollback()
                return O.error(msg="Job %s not found" % job_name)
        return O.error(msg="Invalid request")

    @jobs.when(method='POST', template='json')
    @jobs.wrap_create()
    def create(self, name=None, **kwargs):
        if not kwargs:
            kwargs = request.json
        name = name or kwargs['name']
        automation = kwargs['automation']
        params = kwargs.get('params')
        if params:
            if not isinstance(params, dict):
                params = json.loads(params)
        else:
            params = {}
        private = (bool(kwargs.get('private'))
                   and not kwargs.get('private') in ['0', 'false', 'False'])

        per = kwargs['period']
        period = Period(per)
        if not period.is_valid():
            return O.error(msg="Period %s is not valid" % period)

        depl = Deployment.my(request).filter(
            Deployment.name == automation).first()
        if not depl:
            return O.error(msg="Invalid Automation name")

        user = request.db.query(User).filter(User.id == request.user.id).one()
        job = Job(name=name, owner=user, enabled=True,
                  params=json.dumps(params), deployment=depl, private=private,
                  exec_period=period._)

        request.db.add(job)
        request.db.commit()
        cron_name = job.uid
        # Post-create
        if not EXE_PATH:
            return O.error(msg="Scheduler job executable not found on server")
        url = EXE_PATH % cron_name
        if job.params:
            url = "%s -e '%s'" % (url, job.params)
        success, res = schedule_manager.add(request.user.username,
                                            cron_name, period, url,
                                            job.name)

    @jobs.when(method='PATCH', template='json')
    @jobs.wrap_update(model_name="Job")
    def patch(self, **kw):
        kwargs = kw or request.json
        name = kwargs.pop('name')

        job = Job.own(request).filter(
            Job.name == name).first()
        if not job:
            return O.error(msg="Job %s not found" % name)

        name_to_update = False
        if kwargs.get('new_name'):
            new_name = kwargs['new_name']
            job.name = new_name
            name_to_update = True

        automation = kwargs.get('automation')
        if automation:
            depl = Deployment.my(request).filter(
                Deployment.name == automation).first()
            if not depl:
                return O.error(msg="Invalid Automation name")
            job.deployment = depl

        period = None
        per = kwargs.get('period')
        period_to_update = False
        if per:
            period = Period(per)
            if not period.is_valid():
                return O.error(msg="Period %s is not valid" % period)

            if period.is_only_minutes() and period.total_minutes < 5:
                return O.error(msg="Period cannot be less than 5 minutes")

        params = kwargs.get('params')
        if params:
            if isinstance(params, dict):
                params = json.dumps(params)
            job.params = params

        if period and period._ != job.exec_period:
            job.exec_period = period._
            period_to_update = True

        enabled = kwargs.get('enabled')
        enable_to_update = False
        if enabled is not None:
            enabled = enabled not in ['0', 'false', 'False']
            if enabled != job.enabled:
                enable_to_update = True
            job.enabled = enabled

        private = kwargs.get('private')
        if private is not None:
            job.private = private not in ['0', 'false', 'False']

        request.db.add(job)
        request.db.commit()

        if period_to_update or name_to_update:
            success, res = schedule_manager.edit(
                request.user.username, job.uid, period, job.name)

        if enable_to_update:
            if job.enabled:
                url = EXE_PATH % job.uid
                schedule_manager.add(request.user.username,
                                     job.uid,
                                     job.exec_period,
                                     url, job.name)
            else:
                schedule_manager.delete(request.user.username, job.uid)

    @jobs.when(method='PUT', template='json')
    def update(self, **kw):
        kwargs = kw or request.json
        try:
            assert kwargs['name']
            assert kwargs['automation']
            assert kwargs['params']
            assert kwargs['period']
            assert kwargs['private']
            assert kwargs['enabled']
            return self.patch(**kwargs)
        except KeyError, kerr:
            return O.error(msg="Value not present: %s" % kerr,
                           field=str(kerr).strip("'"))

    @jobs.when(method='DELETE', template='json')
    @jobs.wrap_delete()
    def delete(self, job_name, **kwargs):
        try:
            job = Job.own(request).filter(
                Job.name == job_name).first()
            if job:
                request.db.delete(job)
            else:
                return O.error(msg="Job %s not found" % job_name)
        except Exception, ex:
            return O.error(msg='%r' % ex)
