from pecan import conf, expose, request
from pecan.hooks import HookController

from cloudrunner_server.api.hooks.error_hook import ErrorHook
from cloudrunner_server.api.hooks.signal_hook import SignalHook, signal
from cloudrunner_server.api.util import JsonOutput as O

sig_manager = conf.signal_manager


class Triggers(HookController):

    __hooks__ = [SignalHook(), ErrorHook()]

    @expose('json', generic=True)
    def bindings(self):
        triggers = []
        user_org = (request.user.username, request.user.org)
        success, res = sig_manager.list(user_org)  # , signal, target, auth)
        if success:
            triggers.extend(res)
        return O.triggers(_list=triggers)

    @bindings.when(method='POST', template='json')
    @signal('triggers.binding', 'attach',
            when=lambda x: x.get("status") == "ok")
    def create(self, signal=None, **kwargs):
        try:
            signal = signal or kwargs['signal']
            target = kwargs['target']
            auth = kwargs.get('auth')
            user_org = (request.user.username, request.user.org)
            success, res = sig_manager.attach(user_org, signal, target, auth)
            if success:
                return dict(status='ok')
            else:
                return dict(error=res)
        except KeyError, kex:
            return dict(error='Value not present: %s' % kex)
        except Exception, ex:
            return dict(error='%r' % ex)

    @bindings.when(method='PUT', template='json')
    @signal('triggers.binding', 'detach',
            when=lambda x: x.get("status") == "ok")
    def detach(self, signal=None, **kwargs):
        try:
            signal = signal or kwargs['signal']
            target = kwargs['target']
            user_org = (request.user.username, request.user.org)
            success, res = sig_manager.detach(user_org, signal, target)
            if success:
                return dict(status='ok')
            else:
                return dict(error=res)
        except KeyError, kex:
            return dict(error='Value not present: %s' % kex)
        except Exception, ex:
            return dict(error='%r' % ex)
