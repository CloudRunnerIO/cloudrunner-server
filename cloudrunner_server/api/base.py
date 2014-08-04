from pecan import response

from cloudrunner_server.api.hooks.zmq_hook import ZmqHook

# class BaseController(HookController):
#    __hooks__ = [ErrorHook()]


class ZmqMixin(object):
    __hooks__ = [ZmqHook()]


class DbMixin(object):
    __hooks__ = []


class SseRenderer(object):

    def __init__(self, path, extra_vars):
        pass

    def render(self, template_path, res):
        _res = []
        if res.id:
            _res.append("id: %s" % res.id)
        if res.event:
            _res.append("event: %s" % res.event)
        _data = res.data
        if _data:
            _res.extend(res.data)

        return response  # "\n".join(_res)
