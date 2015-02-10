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

import hashlib
import logging
import requests
from pecan import conf, expose, request, render
from pecan.hooks import HookController
from sqlalchemy.exc import IntegrityError

from cloudrunner_server.api.decorators import wrap_command
from cloudrunner_server.api.hooks.braintree_hook import BrainTreeHook
from cloudrunner_server.api.hooks.db_hook import DbHook
from cloudrunner_server.api.hooks.error_hook import ErrorHook
from cloudrunner_server.api.util import JsonOutput as O
from cloudrunner_server.api.model import *  # noqa

from cloudrunner_server.master.functions import CertController
from cloudrunner_server.util.cache import CacheRegistry

DEFAULT_EXP = 1440
LOG = logging.getLogger()
MAX_EXP = 3 * 30 * 24 * 60  # 3 months/90 days


@event.listens_for(Org, 'after_insert')
def org_after_insert(mapper, connection, target):
    try:
        ccont = CertController(conf.cr_config, db=connection)
        ccont.create_ca(target.name)
    except Exception, ex:
        if LOG:
            LOG.exception(ex)


class Auth(HookController):

    __hooks__ = [DbHook(), ErrorHook(), BrainTreeHook()]

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
            t = request.db.query(Token).filter(
                Token.value == token, Token.scope == 'RECOVER').first()
            if not t:
                return O.error(msg="The recovery key is invalid "
                               "or expired.")
            username = t.user.username
            t.user.set_password(password)
            request.db.add(t.user)
            request.db.delete(t)
            request.db.commit()

        user = request.db.query(User).join(Org).outerjoin(
            Token, Permission).filter(
                User.enabled == True,  # noqa
                User.username == username,
                User.password == hash_token(password)).first()
        if not user:
            return O.error(msg='Cannot login')

        try:
            expire = int(expire)
            if expire < 0 or expire > MAX_EXP:
                return O.error(msg='Invalid expire timeout, '
                               'should be between 1 and %d minutes' % MAX_EXP)
        except:
            expire = DEFAULT_EXP
        token = User.create_token(request, user.id,
                                  minutes=expire,
                                  scope='LOGIN')

        permissions = [p.name for p in user.permissions]
        md = hashlib.md5()
        md.update(user.email)
        email_hash = md.hexdigest()
        cached_token = dict(uid=user.id, org=user.org.name, token=token.value,
                            tier=user.org.tier.serialize(skip=['id']),
                            permissions=permissions, email=user.email,
                            email_hash=email_hash)

        cache = CacheRegistry()
        cache.add_token(username, cached_token, expire)

        return O.login(user=username,
                       email_hash=email_hash,
                       token=token.value,
                       expire=token.expires_at,
                       org=user.org.name,
                       perms=permissions)

    @expose('json')
    def logout(self):
        """
        .. http:get:: /auth/logout/

        Log out the user

        """
        user = (request.headers.get('Cr-User')
                or request.headers.get('X-Cr-User'))
        token = (request.headers.get('Cr-Token')
                 or request.headers.get('X-Cr-Token'))

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
                cache = CacheRegistry()
                cache.revoke_token(token)
        return O.error(msg="Cannot logout")

    @expose('json')
    def payment_token(self):
        token = request.braintree.ClientToken.generate()
        return O.payment(token=token)

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
        org = Org(name="ORG-%s" % username, tier=plan, enabled=True)
        user = User(username=username, email=email, org=org,
                    first_name=kwargs["first_name"],
                    last_name=kwargs["last_name"],
                    department=kwargs.get("department"),
                    position=kwargs.get("position"),
                    enabled=False)
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

        # Billing
        token = kwargs.get('payment_nonce')
        customer_reply = request.braintree.Customer.create({
            "first_name": kwargs['first_name'],
            "last_name": kwargs['last_name'],
            "email": email,
            "credit_card": {
                "payment_method_nonce": token,
                "options": {
                    "verify_card": True,
                }
            }
        })
        if plan_id != 'free':
            if customer_reply.is_success:
                customer = request.braintree.Customer.find(
                    customer_reply.customer.id)
                token = customer.credit_cards[0].token
                request.braintree.Subscription.create({
                    "payment_method_token": token,
                    "plan_id": plan_id
                })
            else:
                for error in customer_reply.errors.deep_errors:
                    print vars(error)

        html = render('email/activate.html',
                      dict(ACTION_URL=ACTION_URL, KEY=key.value))
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
            ApiKey.value == key, ApiKey.enabled == True).one()  # noqa
        user.enabled = True
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
