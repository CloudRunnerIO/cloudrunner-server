import logging
from httplib2 import urllib
from pecan import conf, expose, request
from pecan.hooks import HookController
from sqlalchemy.orm import exc

from cloudrunner_server.api.hooks.error_hook import ErrorHook
from cloudrunner_server.api.hooks.db_hook import DbHook
from cloudrunner_server.api.hooks.signal_hook import SignalHook, signal
from cloudrunner_server.api.hooks.user_hook import UserHook
from cloudrunner_server.api.hooks.zmq_hook import ZmqHook
from cloudrunner_server.api.model import (Job, User, Script,
                                          Org, SOURCE_TYPE)
from cloudrunner_server.api.v0_9.controllers.dispatch import Dispatch
from cloudrunner_server.api.util import (JsonOutput as O,
                                         Wrap)

sig_manager = conf.signal_manager
schedule_manager = conf.schedule_manager
user_manager = conf.auth_manager

JOB_FIELDS = ('name', 'target', 'arguments', 'enabled', 'private')
LOG = logging.getLogger()


class TriggerSwitch(HookController):

    __hooks__ = [ZmqHook(), UserHook(), SignalHook(), ErrorHook(), DbHook()]

    @expose('json', generic=True)
    def index(self, user=None, token=None, trigger=None, key=None, **kwargs):
        if not user:
            return O.error(msg="Unauthorized request")

        LOG.info("Received trigger event(user: %s, trigger: %s) from: %s" % (
            user, trigger, request.client_addr))

        if not token:
            # Check for external job
            j = request.db.query(Job).join(User).filter(
                Job.name == trigger,
                Job.source == SOURCE_TYPE.EXTERNAL,
                User.username == user,
                Job.arguments == key).first()
            if not j:
                return O.error("Invalid request")

            (token, expires) = user_manager.create_token(
                user, "", expiry=30)

        user_id, access_map = user_manager.validate(
            user, token)

        if not user_id or not access_map:
            return O.error(msg="Unauthorized request")

        request.user = Wrap(id=user_id,
                            username=user,
                            org=access_map.org,
                            token=token)

        q = Job.active(request).filter(
            Job.name == trigger)
        d = Dispatch()
        request.reset_zmq(user, token)
        results = []
        for trig in q.all():
            if (trig.source == SOURCE_TYPE.EXTERNAL
                and trig.arguments == key) or (trig.key == key):

                    results.append(dict(id=trig.id,
                                        name=trig.name,
                                        result=d.execute(
                                        data=trig.target.content,
                                        source=trig.target.name,
                                        source_type=2,
                                        **kwargs)))

        return O.result(runs=results, trigger=trigger)


class Triggers(HookController):

    __hooks__ = [UserHook(), SignalHook(), ErrorHook(), DbHook()]

    @expose('json', generic=True)
    def jobs(self, *args, **kwargs):
        if not args:
            triggers = []
            query = Job.visible(request)
            triggers = [t.serialize(
                skip=['owner_id', 'target_id'],
                rel=[('owner.username', 'owner'),
                     ('target.name', 'script'),
                     ('target.folder.library.name', 'library'),
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
                         ('target.folder.library.name', 'library'),
                         ('target.folder.full_name', 'path')]))
            except exc.NoResultFound, ex:
                LOG.error(ex)
                request.db.rollback()
                return O.error("Job %s not found" % name)
        return O.error("Invalid request")

    @jobs.when(method='POST', template='json')
    @signal('triggers.jobs', 'attach',
            when=lambda x: x.get("status") == "ok")
    def create(self, name=None, **kwargs):
        try:
            name = name or kwargs['name']
            source = kwargs['source']
            target = kwargs['target']
            if target:
                target = target.lstrip('/')
            args = kwargs['args']
            tags = kwargs.get('tags') or []

            tags.extend(["Scheduler", name])

            try:
                source = int(source)
                SOURCE_TYPE.from_value(source)
            except:
                return O.error(msg="Invalid source: %s" % source)
            job = Job(name=name, owner_id=request.user.id, enabled=True,
                      source=kwargs['source'],
                      arguments=args)

            script = Script.find(request, target).first()
            if script:
                job.target = script

            request.db.add(job)
            request.db.commit()
            # Post-create
            if source == SOURCE_TYPE.CRON:
                # CRON
                (token, expires) = user_manager.create_token(
                    request.user.username, "", expiry=99999999)
                exec_ = {"exec": 'curl '
                         '%sfire/?user=%s\&token=%s\&'
                         'trigger=%s\&key=%s\&tags=%s '
                         % (conf.REST_SERVER_URL,
                            urllib.quote(request.user.username),
                            token,
                            urllib.quote(job.name),
                            urllib.quote(job.key),
                            ",".join(urllib.quote(t) for t in tags))}
                success, res = schedule_manager.add(
                    request.user.username,
                    name=name,
                    period=args,
                    auth_token=token,
                    **exec_)
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
                pass
            return O.success(status='ok')
        except KeyError, kex:
            request.db.rollback()
            return O.error(msg='Value not present: %s' % kex)
        except Exception, ex:
            LOG.exception(ex)
            request.db.rollback()
            return O.error(msg='%r' % ex)

    @jobs.when(method='PATCH', template='json')
    @signal('triggers.jobs', 'update',
            when=lambda x: x.get("status") == "ok")
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

            for k, v in kwargs.items():
                if k in JOB_FIELDS and v is not None and hasattr(job, k):
                    setattr(job, k, v)

            request.db.add(job)
            request.db.commit()

            if job.source == SOURCE_TYPE.CRON:
                # CRON
                success, res = schedule_manager.edit(
                    request.user.username,
                    name=job.name,
                    period=job.arguments)
            return O.success(status='ok')
        except KeyError, kex:
            request.db.rollback()
            return O.error(msg="Value not present: '%s'" % kex, field=kex)
        except Exception, ex:
            LOG.exception(ex)
            request.db.rollback()
            return O.error(msg='%r' % ex)

    @jobs.when(method='PUT', template='json')
    @signal('triggers.jobs', 'update',
            when=lambda x: x.get("status") == "ok")
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
    @signal('triggers.jobs', 'delete',
            when=lambda x: x.get("status") == "ok")
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
