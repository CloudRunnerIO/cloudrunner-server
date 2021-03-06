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
from os import path, unlink

from cloudrunner_server.api.decorators import wrap_command, DUPL_SEARCH2
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
CR_LIBRARY = "cloudrunner-library"
ERR_REGISTER_USERNAME = ("Ouch, someone already registered that username. "
                         "Please choose another.")
ERR_REGISTER_EMAIL = ("The email is already registered. "
                      "Please, sign-in.")
ERR_REGISTER_UNKNOWN = ("Ouch, cannot register user. Try again "
                        "later or contact us for help.")


@event.listens_for(Org, 'before_insert')
def org_before_insert(mapper, connection, target):
    try:
        ccont = CertController(conf.cr_config, db=connection)
        ccont.create_ca(target.name)

        ca_dir = path.join(ccont.ca_path, 'org')

        org_priv_key_file = path.join(ca_dir, target.name + '.key')
        org_crt_file = path.join(ca_dir, target.name + ".ca.crt")

        target.cert_ca = open(org_crt_file).read()
        target.cert_key = open(org_priv_key_file).read()
        unlink(org_crt_file)
        unlink(org_priv_key_file)
    except Exception, ex:
        if LOG:
            LOG.error("Cannot create certificates for org %s" % target.name)
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
                       email=user.email,
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

        # Attach cloudrunner-library repo
        check_existing = request.db.query(Repository).filter(
            Repository.type == 'github',
            Repository.org_id == None,
            Repository.name == CR_LIBRARY).first()  # noqa
        if check_existing:
            repository = check_existing
        else:
            repository = Repository(name=CR_LIBRARY, private=False,
                                    type='github')
            request.db.add(repository)
            root = Folder(name="/", full_name="/", repository=repository)
            request.db.add(root)

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
        adm_role = Role(servers="*", as_user="@")
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

        repository_link = Repository(name=CR_LIBRARY, private=False,
                                     type='github',
                                     owner=user,
                                     org=org)
        repository_link.linked = repository
        request.db.add(repository_link)

        auth_user = 'CloudRunnerIO'
        auth_pass = ''
        auth_args = ''
        creds = RepositoryCreds(provider='github', auth_user=auth_user,
                                auth_pass=auth_pass, auth_args=auth_args,
                                repository=repository_link)
        request.db.add(creds)

        try:
            request.db.commit()
        except IntegrityError, ierr:
            if hasattr(ierr, 'orig'):
                LOG.error(ierr.orig)
            else:
                LOG.error(vars(ierr))
            request.db.rollback()
            try_find = DUPL_SEARCH2.findall(str(ierr))
            if try_find and len(try_find[0]) == 2:
                if try_find[0][0] == "name":
                    return O.error(
                        msg=ERR_REGISTER_USERNAME, reason="duplicate")
                elif try_find[0][0] == "email":
                    return O.error(
                        msg=ERR_REGISTER_EMAIL, reason="duplicate")
                else:
                    return O.error(msg=ERR_REGISTER_UNKNOWN,
                                   reason="duplicate")
            elif "uq_organizations_name" in str(ierr):
                return O.error(
                    msg=ERR_REGISTER_USERNAME, reason="duplicate")
            elif "uq_users_email" in str(ierr):
                return O.error(
                    msg=ERR_REGISTER_EMAIL, reason="duplicate")
            else:
                return O.error(msg=ERR_REGISTER_UNKNOWN, reason="duplicate")
        except:
            raise
        # send validation email

        ACTION_URL = "%s/index.html#activate/%s/%s" % (
            conf.DASH_SERVER_URL.rstrip('/'), user.username, key.value)

        # Billing
        token = kwargs.get('payment_nonce')
        args = {
            "first_name": kwargs['first_name'],
            "last_name": kwargs['last_name'],
            "email": email,
        }
        if token:
            args['credit_card'] = {
                "payment_method_nonce": token,
                "options": {
                    "verify_card": True,
                }
            }

        customer_reply = request.braintree.Customer.create(args)
        if plan_id != 'free':
            if customer_reply.is_success:
                customer = request.braintree.Customer.find(
                    customer_reply.customer.id)
                if customer.credit_cards:
                    token = customer.credit_cards[0].token
                    request.braintree.Subscription.create({
                        "payment_method_token": token,
                        "plan_id": plan_id
                    })
            else:
                for error in customer_reply.errors.deep_errors:
                    print vars(error)

        bcc = []
        if hasattr(conf, "registration_bcc") and conf.registration_bcc:
            bcc = [conf.registration_bcc]

        html = render('email/activate.html',
                      dict(ACTION_URL=ACTION_URL, KEY=key.value))
        requests.post(
            "https://api.mailgun.net/v2/cloudrunner.io/messages",
            auth=("api", "key-276qmsiyxi8z5tvie2bvxm2jhfxkhjh9"),
            data={"from": "CloudRunner.IO Team <no-reply@cloudrunner.io>",
                  "to": [email],
                  "bcc": [bcc],
                  "subject": "[CloudRunner.IO] Complete your registration",
                  "html": html})

        return O.success(msg="Check your email how to activate your account")

    @expose('json')
    @wrap_command(User, method='activate', model_name='Account')
    def activate(self, **kwargs):
        if request.method != "POST":
            return O.none()
        if not kwargs:
            kwargs = request.json
        username = kwargs['user']
        key = kwargs['code']
        user = request.db.query(User).join(Org, ApiKey).filter(
            User.username == username,
            ApiKey.value == key, ApiKey.enabled == True).first()  # noqa
        if not user:
            user = request.db.query(User).join(Org, ApiKey).filter(
                User.username == username,
                User.enabled == True).first()  # noqa
            if user:
                return O.error(msg="Already enabled")
            else:
                return O.error(msg="User not found")

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
