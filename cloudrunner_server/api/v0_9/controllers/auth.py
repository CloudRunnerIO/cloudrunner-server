import time
from datetime import datetime
from pecan import conf, expose, request
from pecan.hooks import HookController

from cloudrunner_server.api.hooks.db_hook import DbHook
from cloudrunner_server.api.hooks.user_hook import UserHook
from cloudrunner_server.api.hooks.error_hook import ErrorHook
from cloudrunner_server.api.util import JsonOutput as O

from cloudrunner_server.api.client import redis_client as r
from cloudrunner_server.api.util import REDIS_AUTH_USER, REDIS_AUTH_TOKEN

DEFAULT_EXP = 1440
user_manager = conf.auth_manager


class Auth(HookController):

    __hooks__ = [UserHook(), DbHook(), ErrorHook()]

    @expose('json')
    def login(self, username, password, expire=DEFAULT_EXP):
        user_id, access_map = user_manager.authenticate(
            username, password)
        if not user_id:
            return O.login(error='Cannot login')

        (token, expires) = user_manager.create_token(username, "",
                                                     expiry=expire)
        key = REDIS_AUTH_TOKEN % username
        ts = time.mktime(expires.timetuple())
        r.zadd(key, token, ts)

        r.hmset(REDIS_AUTH_USER % username,
                dict(uid=str(user_id), org=access_map.org))
        return O.login(user=username,
                       token=token,
                       expire=expires,
                       org=access_map.org)

    @expose('json')
    def logout(self):
        user = request.headers.get('Cr-User')
        token = request.headers.get('Cr-Token')

        try:
            if user and token:
                success, msg = user_manager.delete_token(user, token)
                if success:
                    return dict(status="ok")
                else:
                    return dict(error=msg)
        finally:
            key = REDIS_AUTH_TOKEN % user
            # Remove current token
            r.zrem(key, token)
            ts_now = time.mktime(datetime.now().timetuple())
            # Remove expired tokens
            r.zremrangebyscore(key, 0, ts_now)
        return dict(error="Cannot logout")
