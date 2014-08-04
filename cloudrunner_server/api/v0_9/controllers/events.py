from pecan import expose, request
from webob import Response
from pecan.hooks import HookController

from cloudrunner_server.api.hooks.error_hook import ErrorHook
from cloudrunner_server.api.hooks.redis_hook import RedisHook
from cloudrunner_server.util.cache import CacheRegistry

MAX_TIMEOUT = 15


class Event(object):

    def __init__(self, retry_after=None, last_event_id=None, event=None):
        self.retry = retry_after
        self._event = ""
        self._data = []
        self.last_event_id = None
        if last_event_id:
            try:
                self.last_event_id = int(last_event_id)
            except ValueError:
                self.last_event_id = None
        if event:
            self._event = event

    @classmethod
    def from_request(cls, request):
        return Event(last_event_id=request.headers.get("Last-Event-Id"))

    @property
    def data(self):
        return "\n".join(self._data)

    def add_line(self, target, value, event_id=None, retry=None):
        if event_id:
            self._data.append("id: %s" % event_id)
        if retry:
            self._data.append("retry: %s" % retry)
        self._data.append("event: %s" % target)
        self._data.append("data: %s" % value)
        self._data.append("")
        self._data.append("")

    def __iter__(self):
        return iter(self.data)


class Events(HookController):

    __hooks__ = [ErrorHook(), RedisHook()]

    @expose(content_type="text/event-stream")
    @expose(content_type="application/json")
    def get(self, org=None, *args, **kwargs):
        targets = kwargs.keys()

        cache = CacheRegistry(redis=request.redis)

        ev = Event.from_request(request)

        for target in targets:
            etag = cache.check(org, target)
            if target == "activities":
                ev.add_line(target, target, etag)
            else:
                ev.add_line(target, target, etag, retry=1000)

        response = Response()
        response.text = unicode(ev.data)
        # response.content_length = 10
        response.content_type = "text/event-stream"
        response.cache_control = "no-cache"
        response.connection = "keep-alive"
        return response  # res
