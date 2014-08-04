import time
from datetime import datetime
from pecan import expose, request
from pecan.secure import secure

from .auth import Auth
from .dispatch import Dispatch
from .events import Events
from .help import HtmlDocs
from .library import Library
from .logs import Logs
from .manage import Manage
from .scheduler import Scheduler
from .triggers import Triggers

from cloudrunner_server.api import VERSION
from cloudrunner_server.api.client import redis_client as r
from cloudrunner_server.api.util import REDIS_AUTH_USER, REDIS_AUTH_TOKEN


class Wrap(object):

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class RestApi(object):

    @classmethod
    def authorize(cls):
        username = request.headers.get('Cr-User')
        token = request.headers.get('Cr-Token')
        if username and token:
            key = REDIS_AUTH_TOKEN % username
            ts_now = time.mktime(datetime.now().timetuple())
            tokens = r.zrangebyscore(key, ts_now, 'inf')
            if token not in tokens:
                return False

            user_info = r.hgetall(REDIS_AUTH_USER % username)
            request.user = Wrap(id=user_info['uid'],
                                username=username,
                                org=user_info['org'],
                                token=token)
            return True
        return False

    @expose('json')
    def version(self):
        return dict(name='CloudRunner.IO REST API', version=VERSION)

    auth = Auth()
    dispatch = secure(Dispatch(), 'authorize')
    library = secure(Library(), 'authorize')
    scheduler = secure(Scheduler(), 'authorize')
    triggers = secure(Triggers(), 'authorize')
    logs = secure(Logs(), 'authorize')
    manage = secure(Manage(), 'authorize')
    #
    # SSE
    #
    events = Events()

    # Docs
    html = HtmlDocs()


class Main(object):
    rest = RestApi()
