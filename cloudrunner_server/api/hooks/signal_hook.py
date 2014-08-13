from functools import wraps
from pecan import conf, request, response  # noqa

from cloudrunner_server.api.hooks.redis_hook import RedisHook


class SignalHook(RedisHook):

    priority = 100

    def after(self, state):
        sig = getattr(state.response, 'fire_up_event', None)
        if sig:
            if conf.app.debug:
                state.response.headers['X-Pecan-Fire-Signal'] = sig
            request.redis.incr(sig)
            request.redis.publish(sig, state.response.fire_up_action)


def signal(event, action, when=None):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            ret = f(*args, **kwargs)
            if not callable(when) or when(ret):
                response.fire_up_event = event
                response.fire_up_action = action
            return ret
        return wrapper
    return decorator
