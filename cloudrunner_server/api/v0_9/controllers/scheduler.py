from pecan import conf, expose, request
from pecan.hooks import HookController

from cloudrunner_server.api.hooks.error_hook import ErrorHook
from cloudrunner_server.api.hooks.signal_hook import SignalHook, signal
from cloudrunner_server.api.util import JsonOutput as O

schedule_manager = conf.schedule_manager


class Scheduler(HookController):

    __hooks__ = [SignalHook(), ErrorHook()]

    @expose('json', generic=True)
    def jobs(self, *args, **kwargs):
        if not args:
            jobs = []
            success, res = schedule_manager.list(request.user.username)
            if success:
                jobs.extend(res)
            return O.jobs(_list=jobs)
        else:
            name = "/".join(args).rstrip('/')
            success, res = schedule_manager.show(request.user.username, name)
            if success:
                    return O.job(**res)
        return O.jobs(_list=[])

    @jobs.when(method='POST', template='json')
    @signal('scheduler.jobs', 'create',
            when=lambda x: x.get("status") == "ok")
    def create(self, name=None, **kwargs):
        try:
            name = name or kwargs['name']
            content = kwargs['content']
            period = kwargs['period']
            success, res = schedule_manager.add(request.user.username,
                                                name=name,
                                                payload=content,
                                                period=period,
                                                auth_token=request.user.token)
            return dict(status='ok')
        except KeyError, kex:
            return dict(error='Value not present: %s' % kex)
        except Exception, ex:
            return dict(error='%r' % ex)

    @jobs.when(method='PUT', template='json')
    @signal('scheduler.jobs', 'update',
            when=lambda x: x.get("status") == "ok")
    def update(self, **kwargs):
        try:
            name = kwargs['name']
            content = kwargs['content']
            period = kwargs['period']
            success, res = schedule_manager.edit(request.user.username,
                                                 name=name,
                                                 payload=content,
                                                 period=period)
            return dict(status='ok')
        except KeyError, kex:
            return dict(error='Value not present: %s' % kex)
        except Exception, ex:
            return dict(error='%r' % ex)

    @jobs.when(method='PATCH', template='json')
    @signal('scheduler.jobs', 'update',
            when=lambda x: x.get("status") == "ok")
    def patch(self, **kwargs):
        kwargs.setdefault('content', None)
        kwargs.setdefault('period', None)

        return self.update(**kwargs)

    @jobs.when(method='DELETE', template='json')
    @signal('scheduler.jobs', 'delete',
            when=lambda x: x.get("status") == "ok")
    def delete(self, name, **kwargs):
        try:
            success, res = schedule_manager.delete(request.user.username,
                                                   name=name)
            return dict(status='ok')
        except KeyError, kex:
            return dict(error='Value not present: %s' % kex)
        except Exception, ex:
            return dict(error='%r' % ex)
