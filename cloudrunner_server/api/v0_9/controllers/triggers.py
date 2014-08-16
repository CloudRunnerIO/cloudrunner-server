from pecan import conf, expose, request
from pecan.hooks import HookController
from sqlalchemy.orm import exc

from cloudrunner_server.api.hooks.error_hook import ErrorHook
from cloudrunner_server.api.hooks.db_hook import DbHook
from cloudrunner_server.api.hooks.signal_hook import SignalHook, signal
from cloudrunner_server.api.model import (Job, User, Script,
                                          Org, SOURCE_TYPE)
from cloudrunner_server.api.util import JsonOutput as O

sig_manager = conf.signal_manager
schedule_manager = conf.schedule_manager


class Triggers(HookController):

    __hooks__ = [SignalHook(), ErrorHook(), DbHook()]

    @expose('json', generic=True)
    def jobs(self, *args, **kwargs):
        if not args:
            triggers = []
            query = request.db.query(Job).join(User, Org).filter(
                Org.name == request.user.org)
            triggers = [t.serialize(
                skip=['id', 'owner_id', 'target_id'],
                rel=[('owner.username', 'owner'),
                     ('target.name', 'script')])
                for t in query.all()]
            return O.triggers(_list=sorted(triggers,
                                           key=lambda t: t['name'].lower()))
        else:
            name = "/".join(args).rstrip('/')
            try:
                job = request.db.query(Job).join(User, Org).filter(
                    Job.name == name, Org.name == request.user.org).one()
                return O.job(**job.serialize(
                    skip=['id', 'owner_id', 'target_id'],
                    rel=[('owner.username', 'owner'),
                         ('target.name', 'script')]))
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
            args = kwargs['args']
            try:
                SOURCE_TYPE.from_value(int(kwargs['source']))
            except:
                return O.error(msg="Invalid source")
            job = Job(name=name, owner_id=request.user.id, enabled=True,
                      source=kwargs['source'],
                      arguments=args)

            script = request.db.query(Script).filter(
                Script.name == target).first()
            if script:
                job.target = script

            if source == '1':
                # CRON
                user_org = (request.user.username, request.user.org)
                # success, res = schedule_manager.add(request.user.username,
                #                                    name=name,
                #                                    payload=content,
                #                                    period=args,
                #                                    auth_token=token,
                #                                    **exec_)
            elif source == '2':
                # ENV
                # Regiter at publisher
                pass
            elif source == '3':
                # LOG
                # Regiter at publisher
                pass
            elif source == '4':
                # EXTERNAL
                pass
            request.db.add(job)
            request.db.commit()
            return dict(status='ok')
        except KeyError, kex:
            request.db.rollback()
            return O.error(msg='Value not present: %s' % kex)
        except Exception, ex:
            request.db.rollback()
            return O.error(msg='%r' % ex)

    @jobs.when(method='PUT', template='json')
    @signal('triggers.jobs', 'update',
            when=lambda x: x.get("status") == "ok")
    def update(self, **kw):
        try:
            kwargs = kw or request.json
            name = kwargs['name']
            content = kwargs['content']
            period = kwargs['period']
            success, res = schedule_manager.edit(request.user.username,
                                                 name=name,
                                                 payload=content,
                                                 period=period)
            if success:
                return dict(status='ok')
            else:
                return dict(error=res)
        except KeyError, kex:
            return dict(error='Value not present: %s' % kex)
        except Exception, ex:
            return dict(error='%r' % ex)

    @jobs.when(method='PATCH', template='json')
    @signal('triggers.jobs', 'update',
            when=lambda x: x.get("status") == "ok")
    def patch(self, **kw):
        kwargs = kw or request.json
        kwargs.setdefault('content', None)
        kwargs.setdefault('period', None)

        return self.update(**kwargs)

    @jobs.when(method='DELETE', template='json')
    @signal('triggers.jobs', 'delete',
            when=lambda x: x.get("status") == "ok")
    def delete(self, name, **kwargs):
        name = name or kwargs['name']
        try:
            job = request.db.query(Job).join(User).filter(
                Job.name == name,
                User.id == request.user.id).first()
            if job:
                request.db.delete(job)
                return dict(status='ok')
            else:
                return dict(error="Trigger %s not found" % name)
        except Exception, ex:
            return dict(error='%r' % ex)
