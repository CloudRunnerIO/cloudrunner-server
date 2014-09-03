#!/usr/bin/python
# -*- coding: utf-8 -*-
# vim: tabstop=4 shiftwidth=4 softtabstop=4

# /*******************************************************
#  * Copyright (C) 2013-2014 CloudRunner.io <info@cloudrunner.io>
#  *
#  * Proprietary and confidential
#  * This file is part of CloudRunner Server.
#  *
#  * CloudRunner Server can not be copied and/or distributed
#  * without the express permission of CloudRunner.io
#  *******************************************************/

import logging
import time
from pecan import expose, request
from pecan.hooks import HookController

from cloudrunner_server.api.hooks.db_hook import DbHook
from cloudrunner_server.api.hooks.error_hook import ErrorHook
from cloudrunner_server.api.util import JsonOutput as O
from cloudrunner_server.api.model import *  # noqa

from cloudrunner_server.api.client import redis_client as r
from cloudrunner_server.api.util import (REDIS_AUTH_USER,
                                         REDIS_AUTH_TOKEN,
                                         REDIS_AUTH_PERMS)

DEFAULT_EXP = 1440
LOG = logging.getLogger()


class Auth(HookController):

    __hooks__ = [DbHook(), ErrorHook()]

    @expose('json')
    def login(self, username, password, expire=DEFAULT_EXP):
        user = request.db.query(User).join(Org, Token, Permission).filter(
            User.username == username,
            User.password == hash_token(password)).first()
        if not user:
            return O.error(msg='Cannot login')

        token = User.create_token(request, user.id,
                                  minutes=expire,
                                  scope='LOGIN')

        key = REDIS_AUTH_TOKEN % username
        ts = time.mktime(token.expires_at.timetuple())
        r.zadd(key, token.value, ts)
        permissions = [p.name for p in user.permissions]
        perm_key = REDIS_AUTH_PERMS % username
        r.delete(perm_key)
        if permissions:
            r.sadd(perm_key, *permissions)
        info_key = REDIS_AUTH_USER % username
        r.delete(info_key)
        r.hmset(info_key, dict(uid=str(user.id), org=user.org.name))

        return O.login(user=username,
                       token=token.value,
                       expire=token.expires_at,
                       org=user.org.name)

    @expose('json')
    def logout(self):
        user = request.headers.get('Cr-User')
        token = request.headers.get('Cr-Token')

        if user and token:
            try:
                tokens = request.db.query(Token).join(User).filter(
                    User.username == user,
                    Token.value == token).all()
                map(request.db.delete, tokens)
                request.db.commit()
                return O.success(status="ok")
            except Exception, ex:
                LOG.error(ex)
                return O.error(msg="Cannot logout")
            finally:
                key = REDIS_AUTH_TOKEN % user
                key_perm = REDIS_AUTH_PERMS % user
                # Remove current token
                r.zrem(key, token)
                r.delete(key_perm)
                ts_now = time.mktime(datetime.now().timetuple())
                # Remove expired tokens
                r.zremrangebyscore(key, 0, ts_now)
        return O.error(msg="Cannot logout")
