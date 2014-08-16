import time

from pecan import conf, expose, request
from pecan.hooks import HookController

from cloudrunner_server.api.hooks.error_hook import ErrorHook
from cloudrunner_server.api.hooks.signal_hook import SignalHook, signal
from cloudrunner_server.api.hooks.user_hook import UserHook
from cloudrunner_server.api.util import (JsonOutput as O,
                                         REDIS_AUTH_USER,
                                         REDIS_AUTH_TOKEN)
from cloudrunner_server.api.client import redis_client as r

schedule_manager = conf.schedule_manager
user_manager = conf.auth_manager


class Scheduler(HookController):

    __hooks__ = [UserHook(), SignalHook(), ErrorHook()]

    @expose('json', generic=True)
    def jobs(self, *args, **kwargs):
        if not args:
            jobs = []
            success, res = schedule_manager.list(request.user.username)
            if success:
                jobs.extend(res)
            return O.jobs(_list=jobs)

    @jobs.when(method='POST', template='json')
    @signal('scheduler.jobs', 'create',
            when=lambda x: x.get("status") == "ok")
    def create(self, name=None, **kw):
        try:
            kwargs = kw or request.json
            name = name or kwargs['name']
            content = kwargs['content']
            period = kwargs['period']
            (token, expires) = user_manager.create_token(
                request.user.username, "", expiry=99999999)
            key = REDIS_AUTH_TOKEN % request.user.username
            ts = time.mktime(expires.timetuple())
            r.zadd(key, token, ts)

            r.hmset(REDIS_AUTH_USER % request.user.username,
                    dict(uid=str(request.user.id), org=request.user.org))

            tags = ["scheduler", name]
            exec_ = {"exec": 'curl -s -H "Cr-User: %s" -H "Cr-Token: %s" '
                     '%sdispatch/execute?tags=%s '
                     '-d data="$(cat %%s)"' % (request.user.username,
                                               token,
                                               conf.REST_SERVER_URL,
                                               ",".join(tags))}
            success, res = schedule_manager.add(request.user.username,
                                                name=name,
                                                payload=content,
                                                period=period,
                                                auth_token=token,
                                                **exec_)
            if success:
                return dict(status='ok')
            else:
                return dict(error=res)
        except KeyError, kex:
            return dict(error='Value not present: %s' % kex)
        except Exception, ex:
            return dict(error='%r' % ex)

    @jobs.when(method='PUT', template='json')
    @signal('scheduler.jobs', 'update',
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
    @signal('scheduler.jobs', 'update',
            when=lambda x: x.get("status") == "ok")
    def patch(self, **kw):
        kwargs = kw or request.json
        kwargs.setdefault('content', None)
        kwargs.setdefault('period', None)

        return self.update(**kwargs)

    @jobs.when(method='DELETE', template='json')
    @signal('scheduler.jobs', 'delete',
            when=lambda x: x.get("status") == "ok")
    def delete(self, name):
        try:
            success, res = schedule_manager.delete(request.user.username,
                                                   name=name)
            if success:
                return dict(status='ok')
            else:
                return dict(error=res)
        except KeyError, kex:
            return dict(error='Value not present: %s' % kex)
        except Exception, ex:
            return dict(error='%r' % ex)
