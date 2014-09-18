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
from httplib2 import Http, urllib, urlparse
from pecan import conf, expose, request
from pecan.hooks import HookController
from sqlalchemy.orm import exc

from cloudrunner_server.api.decorators import wrap_command
from cloudrunner_server.api.hooks.error_hook import ErrorHook
from cloudrunner_server.api.hooks.db_hook import DbHook
from cloudrunner_server.api.hooks.perm_hook import PermHook
from cloudrunner_server.api.hooks.signal_hook import SignalHook
from cloudrunner_server.api.model import (Job, User, Script, Permission,
                                          SOURCE_TYPE)
from cloudrunner_server.api.util import (JsonOutput as O,
                                         Wrap)
from cloudrunner_server.triggers.manager import TriggerManager

schedule_manager = conf.schedule_manager

JOB_FIELDS = ('name', 'target', 'arguments', 'enabled', 'private')
LOG = logging.getLogger()


class TriggerSwitch(HookController):

    __hooks__ = [SignalHook(), ErrorHook(), DbHook()]

    @expose('json')
    def index(self, user=None, token=None, trigger=None, key=None, **kwargs):
        LOG.info("Received trigger event(trigger: %s) from: %s" % (
            trigger, request.client_addr))

        q = request.db.query(Job).join(User, Permission).filter(
            Job.name == trigger,
            Job.key == key,
            Job.source == SOURCE_TYPE.EXTERNAL)

        man = TriggerManager()
        results = []
        for trig in q.all():
            if not trig.target:
                LOG.warning("Empty trigger: %s" % trig.name)
                continue

            u = trig.owner
            permissions = [p.name for p in u.permissions]

            request.user = Wrap(id=u.id,
                                username=u.username,
                                org=u.org.name,
                                permissions=permissions)

            hook = PermHook(dont_have=set(['is_super_admin']))
            hook.before(None)

            env = urlparse.parse_qs(trig.arguments)
            env.update(kwargs)
            res = man.execute(user_id=u.id,
                              script_name=trig.target.full_path(),
                              job=trig,
                              env=env, **kwargs)
            d = dict(id=trig.id, name=trig.name)
            d.update(res)
            results.append(d)

        return O.result(runs=results, trigger=trigger)


class Triggers(HookController):

    __hooks__ = [SignalHook(), ErrorHook(), DbHook(),
                 PermHook(dont_have=set(['is_super_admin']))]

    @expose('json', generic=True)
    @wrap_command(Job, model_name="trigger")
    def jobs(self, *args, **kwargs):
        if not args:
            triggers = []
            query = Job.visible(request)
            triggers = [t.serialize(
                skip=['owner_id', 'target_id'],
                rel=[('owner.username', 'owner'),
                     ('target.name', 'script'),
                     ('target.folder.repository.name', 'repository'),
                     ('target.folder.full_name', 'path')])
                for t in query.all()]
            return O.triggers(_list=sorted(triggers,
                                           key=lambda t: t['name'].lower()))
        else:
            job_id = args[0]
            try:
                job = Job.visible(request).filter(Job.id == job_id).one()
                return O.job(**job.serialize(
                    skip=['key', 'owner_id', 'target_id'],
                    rel=[('owner.username', 'owner'),
                         ('target.name', 'script'),
                         ('target.folder.repository.name', 'repository'),
                         ('target.folder.full_name', 'path')]))
            except exc.NoResultFound, ex:
                LOG.error(ex)
                request.db.rollback()
                return O.error("Job %s not found" % job_id)
        return O.error("Invalid request")

    @jobs.when(method='POST', template='json')
    @jobs.wrap_create()
    def create(self, name=None, **kwargs):
        name = name or kwargs['name']
        source = kwargs['source']
        target = kwargs['target']
        if target:
            target = target.lstrip('/')
        args = kwargs['arguments']
        tags = kwargs.get('tags') or []

        try:
            source = int(source)
            SOURCE_TYPE.from_value(source)
        except:
            return O.error(msg="Invalid source: %s" % source)
        job = Job(name=name, owner_id=request.user.id, enabled=True,
                  source=source,
                  arguments=args)

        script = Script.find(request, target).first()
        if script:
            job.target = script

        request.db.add(job)
        request.db.commit()
        request._model_id = job.id
        # Post-create
        url = ('%(rest)sfire/?trigger='
               '%(trigger)s&key=%(key)s&tags=%(tags)s&%(args)s ')
        kw = dict(rest=conf.REST_SERVER_URL,
                  trigger=urllib.quote(job.name),
                  key=urllib.quote(job.key),
                  args='')
        if source == SOURCE_TYPE.CRON:
            # CRON
            tags.extend(["Scheduler", name])
            kw['tags'] = ",".join([urllib.quote(t) for t in tags])
            success, res = schedule_manager.add(
                request.user.username,
                name=name,
                period=args,
                url=url % kw)
        elif source == SOURCE_TYPE.ENV:
            # ENV
            # Regiter at publisher
            pass
        elif source == SOURCE_TYPE.LOG_CONTENT:
            # LOG
            # Regiter at publisher
            pass
        elif source == SOURCE_TYPE.EXTERNAL:
            # EXTERNAL
            tags.extend(["External", "Trigger", name])
            kw['tags'] = ",".join([urllib.quote(t) for t in tags])
            safe_args = urllib.urlencode(urlparse.parse_qsl(job.arguments))
            kw['args'] = safe_args
            headers = {'Content-type': 'application/x-www-form-urlencoded'}
            try:
                header, body = None, None
                header, body = Http(timeout=5).request(
                    'http://crun.me', 'POST',
                    body=urllib.urlencode({'url': url % kw}),
                    headers=headers)
                job.share_url = json.loads(body)['url']
            except Exception, ex:
                LOG.exception(ex)
                LOG.warn("Shortening service is not reachable: %s" % body)
                job.share_url = url % kw
            request.db.add(job)

    @jobs.when(method='PATCH', template='json')
    @jobs.wrap_update()
    def patch(self, name=None, **kw):
        try:
            kwargs = kw or request.json
            name = name or kwargs.pop('name')

            job = Job.own(request).filter(
                Job.name == name).first()
            if not job:
                return O.error(msg="Job %s not found" % name)

            if 'source' in kwargs:
                try:
                    job.source = int(kwargs.pop('source'))
                except:
                    request.db.rollback()
                    return O.error(msg="Invalid source", field='source')
            if 'target' in kwargs:
                target = kwargs.pop('target').lstrip('/')
                script = Script.find(request, target).first()
                if script:
                    job.target = script
                else:
                    return O.error(msg="Invalid target", field='target')

            changes = []
            for k, v in kwargs.items():
                if k in JOB_FIELDS and v is not None and hasattr(job, k):
                    if getattr(job, k) != v:
                        setattr(job, k, v)
                        changes.append(k)

            if job.source == SOURCE_TYPE.CRON:
                # CRON
                success, res = schedule_manager.edit(
                    request.user.username,
                    name=job.name,
                    period=job.arguments)
            elif job.source == SOURCE_TYPE.EXTERNAL:
                # EXTERNAL
                url = ('%(rest)sfire/?trigger='
                       '%(trigger)s&key=%(key)s&tags=%(tags)s&%(args)s ')
                tags = ["External", "Trigger", job.name]
                kw = dict(rest=conf.REST_SERVER_URL,
                          trigger=urllib.quote(job.name),
                          key=urllib.quote(job.key),
                          args="")
                kw['tags'] = ",".join([urllib.quote(t) for t in tags])
                arguments = kwargs.pop('arguments')
                if 'arguments' in changes:
                    safe_args = urllib.urlencode(urlparse.parse_qsl(arguments))
                    kw['args'] = safe_args
                headers = {'Content-type': 'application/x-www-form-urlencoded'}
                try:
                    header, body = None, None
                    header, body = Http().request(
                        'http://crun.me', 'POST',
                        body=urllib.urlencode({'url': url % kw}),
                        headers=headers)
                    job.share_url = json.loads(body)['url']
                except Exception, ex:
                    LOG.exception(ex)
                    LOG.warn("Shortening service is not reachable: %s" % body)
                    job.share_url = url % kw

            request.db.add(job)

            return O.success(status='ok')
        except KeyError, kex:
            request.db.rollback()
            return O.error(msg="Value not present: '%s'" % kex, field=kex)
        except Exception, ex:
            LOG.exception(ex)
            request.db.rollback()
            return O.error(msg='%r' % ex)

    @jobs.when(method='PUT', template='json')
    def update(self, **kw):
        kwargs = kw or request.json
        try:
            assert kwargs['name']
            assert kwargs['source']
            assert kwargs['arguments']
            assert kwargs['enabled']
            return self.patch(**kwargs)
        except KeyError, kerr:
            return O.error(msg="Value not present: '%s'" % kerr,
                           field=str(kerr))

    @jobs.when(method='DELETE', template='json')
    @jobs.wrap_delete()
    def delete(self, job_id, **kwargs):
        try:
            job = Job.own(request).filter(
                Job.id == job_id).first()
            if job:
                # Cleanup
                if job.source == SOURCE_TYPE.CRON:
                    # CRON
                    success, res = schedule_manager.delete(
                        user=request.user.username, name=job.name)
                elif job.source == SOURCE_TYPE.ENV:
                    # ENV
                    # Regiter at publisher
                    pass
                elif job.source == SOURCE_TYPE.LOG_CONTENT:
                    # LOG
                    # Regiter at publisher
                    pass
                elif job.source == SOURCE_TYPE.EXTERNAL:
                    # EXTERNAL
                    pass

                request.db.delete(job)
                return O.success(status='ok')
            else:
                return O.error(msg="Trigger %s not found" % job_id)
        except Exception, ex:
            return O.error(msg='%r' % ex)
