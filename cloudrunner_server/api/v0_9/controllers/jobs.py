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

from httplib2 import Http, urllib, urlparse
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
from cloudrunner_server.api.hooks.signal_hook import SignalHook
from cloudrunner_server.api.model import (Job, Script,
                                          Folder, Revision, Repository)
from cloudrunner_server.api.util import JsonOutput as O
from cloudrunner_server.plugins.repository.base import PluginRepoBase

schedule_manager = conf.schedule_manager

JOB_FIELDS = ('name', 'target', 'arguments', 'enabled', 'private')
LOG = logging.getLogger()


def _get_script_data(r):
    full_path = r.script.full_path()
    path, _, name = full_path.rpartition('/')
    return dict(path="/%s/" % path, name=name)


def _try_load(s):
    try:
        return json.loads(s)
    except:
        return s


class Jobs(HookController):

    __hooks__ = [SignalHook(), ErrorHook(), DbHook(),
                 PermHook(dont_have=set(['is_super_admin']))]

    @expose('json', generic=True)
    @wrap_command(Job, model_name="Job")
    def jobs(self, *args, **kwargs):
        if not args:
            jobs = []
            query = Job.visible(request)
            jobs = [t.serialize(
                skip=['id', 'key', 'owner_id', 'revision_id'],
                rel=[('owner.username', 'owner'),
                     ('params', 'params', _try_load),
                     ('script', 'script', _get_script_data)])
                    for t in query.all()]
            return O._anon(jobs=sorted(jobs, key=lambda t: t['name'].lower()),
                           quota=dict(allowed=request.tier.cron_jobs))
        else:
            job_name = args[0]
            try:
                job = Job.visible(request).filter(Job.name == job_name).one()
                return O.job(**job.serialize(
                    skip=['id', 'key', 'owner_id', 'revision_id'],
                    rel=[('owner.username', 'owner'),
                         ('params', 'params', _try_load),
                         ('script', 'script', _get_script_data)]))
            except exc.NoResultFound, ex:
                LOG.error(ex)
                request.db.rollback()
                return O.error(msg="Job %s not found" % job_name)
        return O.error(msg="Invalid request")

    @jobs.when(method='POST', template='json')
    @jobs.wrap_create()
    def create(self, name=None, **kwargs):
        name = name or kwargs['name']
        script = kwargs['script']
        version = kwargs.get('version')
        params = kwargs.get('params')
        if params:
            params = json.loads(params)
        else:
            params = {}
        period = kwargs['period']
        private = (bool(kwargs.get('private'))
                   and not kwargs.get('private') in ['0', 'false', 'False'])

        script = script.strip("/")
        repo, _, script_path = script.partition("/")
        _dir, _, script_name = script_path.rpartition("/")
        if not _dir:
            _dir = "/"
        scr = Script.visible(request, repo, _dir).filter(
            Script.name == script_name).one()
        if version:
            rev = [r for r in scr.history if r.version == version]
        else:
            rev = sorted(scr.history,
                         key=lambda x: x.created_at, reverse=True)[0]
        if not rev:
            return O.error("Invalid script/version")

        job = Job(name=name, owner_id=request.user.id, enabled=True,
                  params=json.dumps(params), script=rev, private=private,
                  exec_period=period)

        request.db.add(job)
        request.db.commit()
        cron_name = job.uid
        # Post-create
        exe_path = os.popen('which cloudrunner-trigger').read().strip()
        if not exe_path:
            return O.error(msg="Scheduler job executable not found on server")
        url = "%s exec %s" % (exe_path, cron_name)
        if job.params:
            url = "%s -e '%s'" % (url, job.params)
        success, res = schedule_manager.add(request.user.username,
                                            cron_name, period, url)

    @jobs.when(method='PATCH', template='json')
    @jobs.wrap_update(model_name="Job")
    def patch(self, **kw):
        kwargs = kw or request.json
        name = kwargs.pop('name')

        job = Job.own(request).filter(
            Job.name == name).first()
        if not job:
            return O.error(msg="Job %s not found" % name)

        if kwargs.get('new_name'):
            new_name = kwargs['new_name']
            job.name = new_name

        _script = kwargs.get('script')

        if _script:
            version = kwargs.get('version')
            script = _script.strip("/")
            _repo, _, script_path = script.partition("/")
            _dir, _, script_name = script_path.rpartition("/")
            repo = Repository.visible(request).filter(
                Repository.name == _repo).first()
            if not repo:
                return O.error(msg="Invalid script: %s" % _script,
                               field='script')
            if not _dir:
                _dir = "/"
            scr = Script.visible(request, _repo, _dir).filter(
                Script.name == script_name).first()
            if not scr:
                return O.error(msg="Invalid script: %s" % _script,
                               field='script')
            if version:
                rev = [r for r in scr.history if r.version == version]
            else:
                rev = sorted(scr.history,
                             key=lambda x: x.created_at, reverse=True)
                if rev:
                    rev = rev[0]

            if repo.type == 'cloudrunner':
                if not rev:
                    return O.error(msg="Invalid script: %s" % _script,
                                   field='script')
            else:
                plugin = PluginRepoBase.find(repo.type)
                if not plugin:
                    return O.error(
                        msg="Cannot find plugin for %s repo" % repo.type,
                        field='script')
                plugin = plugin(repo.credentials.auth_user,
                                repo.credentials.auth_pass)
                content, last_modified, rev = plugin.contents(
                    "/".join([_dir, script_name]), rev=version)
                if content is None:
                    return O.error(
                        msg="Cannot load script content for %s" % _script,
                        field='script')

            job.script = rev

        params = kwargs.get('params')
        if params:
            if isinstance(params, dict):
                params = json.dumps(params)
            job.params = params

        period = kwargs.get('period')
        period_to_update = False
        if period and period != job.exec_period:
            job.exec_period = period
            period_to_update = True

        enabled = kwargs.get('enabled')
        if enabled is not None:
            job.enabled = enabled not in ['0', 'false', 'False']

        private = kwargs.get('private')
        if private is not None:
            job.private = private not in ['0', 'false', 'False']

        request.db.add(job)
        request.db.commit()

        if period_to_update:
            success, res = schedule_manager.edit(
                request.user.username,
                name=job.uid,
                period=period)

    @jobs.when(method='PUT', template='json')
    def update(self, **kw):
        kwargs = kw or request.json
        try:
            assert kwargs['name']
            assert kwargs['script']
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
                # Cleanup
                success, res = schedule_manager.delete(
                    user=request.user.username, name=job.uid)

                request.db.delete(job)
            else:
                return O.error(msg="Job %s not found" % job_name)
        except Exception, ex:
            return O.error(msg='%r' % ex)
