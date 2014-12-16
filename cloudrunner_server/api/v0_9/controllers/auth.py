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
import requests
import time
from pecan import conf, expose, request, render
from pecan.hooks import HookController
from sqlalchemy.exc import IntegrityError

from cloudrunner_server.api.decorators import wrap_command
from cloudrunner_server.api.hooks.db_hook import DbHook
from cloudrunner_server.api.hooks.error_hook import ErrorHook
from cloudrunner_server.api.util import JsonOutput as O
from cloudrunner_server.api.model import *  # noqa

from cloudrunner_server.api.client import redis_client as r
from cloudrunner_server.api.util import (REDIS_AUTH_USER,
                                         REDIS_AUTH_TOKEN,
                                         REDIS_AUTH_PERMS,
                                         REDIS_AUTH_TIER)

DEFAULT_EXP = 1440
LOG = logging.getLogger()


class Auth(HookController):

    __hooks__ = [DbHook(), ErrorHook()]

    @expose('json')
    def login(self, **kwargs):

        if not kwargs:
            kwargs = request.json

        username = kwargs.get('username')
        password = kwargs['password']
        token = kwargs.get('token')
        expire = int(kwargs.get('expire', DEFAULT_EXP))
        if not username and token:
            # Recover
            t = request.db.query(Token).filter(Token.value == token,
                                               Token.scope == 'RECOVER').one()
            username = t.user.username
            t.user.set_password(password)
            request.db.add(t.user)
            request.db.delete(t)
            request.db.commit()

        user = request.db.query(User).join(Org).outerjoin(
            Token, Permission).filter(
                User.active == True,  # noqa
                User.username == username,
                User.password == hash_token(password)).first()
        if not user:
            return O.error(msg='Cannot login')

        try:
            expire = int(expire)
        except:
            expire = DEFAULT_EXP
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

        tier_key = REDIS_AUTH_TIER % username
        r.delete(tier_key)
        r.hmset(tier_key, user.org.tier.serialize(skip=['id']))

        return O.login(user=username,
                       token=token.value,
                       expire=token.expires_at,
                       org=user.org.name,
                       perms=permissions)

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

    @expose('json')
    @wrap_command(User, method='create')
    def register(self, **kwargs):
        if request.method != "POST":
            return O.none()
        if not kwargs:
            kwargs = request.json

        plan_id = kwargs["plan_id"]
        username = kwargs["username"]
        password = kwargs["password"]
        email = kwargs["email"]

        plan = request.db.query(UsageTier).filter(
            UsageTier.name == plan_id).one()
        org = Org(name="ORG-%s" % username, tier=plan, active=True)
        user = User(username=username, email=email, org=org,
                    first_name=kwargs.get("first_name"),
                    last_name=kwargs.get("last_name"),
                    department=kwargs.get("department"),
                    position=kwargs.get("position"),
                    active=False)
        user.set_password(password)

        key = ApiKey(user=user)
        adm_role = Role(servers="*", as_user="root")
        perm = Permission(name="is_admin", user=user)
        group = Group(org=org, name="Default")
        group.users.append(user)
        group.roles.append(adm_role)

        request.db.add(org)
        request.db.add(user)
        request.db.add(group)
        request.db.add(adm_role)
        request.db.add(perm)
        request.db.add(key)
        try:
            request.db.commit()
        except IntegrityError, ierr:
            LOG.error(ierr)
            request.db.rollback()
            return O.error(msg="Duplicate", reason="duplicate")
        except:
            raise
        # send validation email

        ACTION_URL = "%s/index.html#activate/%s" % (
            conf.DASH_SERVER_URL.rstrip('/'), key.value)
        html = render('email/activate.html',
                      dict(ACTION_URL=ACTION_URL))
        requests.post(
            "https://api.mailgun.net/v2/cloudrunner.io/messages",
            auth=("api", "key-276qmsiyxi8z5tvie2bvxm2jhfxkhjh9"),
            data={"from": "CloudRunner.IO Team <no-reply@cloudrunner.io>",
                  "to": [email],
                  "subject": "[CloudRunner.IO] Complete your registration",
                  "html": html})

        return O.success(msg="Check your email how to activate your account")

    @expose('json')
    @wrap_command(User, method='create', model_name='Account')
    def activate(self, **kwargs):
        if request.method != "POST":
            return O.none()
        if not kwargs:
            kwargs = request.json
        key = kwargs['code']
        user = request.db.query(User).join(Org, ApiKey).filter(
            ApiKey.value == key).one()
        user.active = True
        api_key = request.db.query(ApiKey).filter(ApiKey.value == key).one()
        new_key = ApiKey(user=user)

        request.db.delete(api_key)
        request.db.add(user)
        request.db.add(new_key)

    @expose('json')
    @wrap_command(User, method='update', model_name='Password')
    def reset(self, email=None, **kwargs):
        if request.method != "POST":
            return O.none()
        if not email:
            email = request.json.get("email")
        user = request.db.query(User).filter(
            User.email == email).first()
        if not user:
            return O.success(msg="Message sent to the specified email.")
        token = User.create_token(request, user.id, scope='RECOVER')

        ACTION_URL = "%s/index.html#page/recovery/%s" % (
            conf.DASH_SERVER_URL.rstrip('/'),
            token.value)
        html = render('email/recover.html',
                      dict(ACTION_URL=ACTION_URL))
        requests.post(
            "https://api.mailgun.net/v2/cloudrunner.io/messages",
            auth=("api", "key-276qmsiyxi8z5tvie2bvxm2jhfxkhjh9"),
            data={"from": "CloudRunner.IO Team <recovery@cloudrunner.io>",
                  "to": [email],
                  "subject": "[CloudRunner.IO] Recover lost password",
                  "html": html})
