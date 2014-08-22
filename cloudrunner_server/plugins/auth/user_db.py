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

from datetime import datetime, timedelta
import logging
import re
from sqlalchemy import create_engine, event
from sqlalchemy.orm import scoped_session, sessionmaker

from cloudrunner.core.message import DEFAULT_ORG
from cloudrunner.util.crypto import hash_token
from cloudrunner_server.plugins.auth.base import AuthPluginBase
from cloudrunner_server.util.db import checkout_listener

from cloudrunner_server.api.model import *  # noqa

TOKEN_LEN = 60
DEFAULT_EXPIRE = 1440  # 24h

LOG = logging.getLogger()


class UserMap(AuthPluginBase):

    def __init__(self, config, db_context=None):
        self.config = config
        if db_context:
            self.db = AuthDb(db_context, self.config.security.use_org)

    def set_context(self, ctx):
        self.db = AuthDb(ctx, self.config.security.use_org)

    def set_context_from_config(self, recreate=False, autocommit=True,
                                **configuration):
        engine = create_engine(self.config.users.db, **configuration)
        if 'mysql+pymysql://' in self.config.users.db:
            event.listen(engine, 'checkout', checkout_listener)
        session = scoped_session(sessionmaker(bind=engine,
                                              autocommit=autocommit))
        metadata.bind = session.bind
        if recreate:
            # For tests: re-create tables
            metadata.create_all(engine)
        self.set_context(session)

    @property
    def db(self):
        if not getattr(self, '_db'):
            raise Exception('DB context not provided')
        return self._db

    @db.setter
    def db(self, db):
        self._db = db

    def authenticate(self, user, password):
        """
        Authenticate using password
        """
        pwd_hash = hash_token(password)
        try:
            (user_id, access_map) = self.db.authenticate(user, pwd_hash)
            return (user_id, access_map)
        except Exception, ex:
            LOG.exception(ex)
            return (None, None)

    def validate(self, user, token):
        """
        Authenticate using issued auth token
        """
        try:
            (user_id, access_map) = self.db.validate(user, token)
            LOG.info("Validated %s:%s" % (user_id, access_map))
            return (user_id, access_map)
        except Exception, ex:
            LOG.exception(ex)
            return (None, None)

    def create_token(self, user, password, **kwargs):
        return self.db.get_token(user,
                                 expiry=kwargs.get('expiry', DEFAULT_EXPIRE))

    def delete_token(self, user, token, **kwargs):
        return self.db.invalidate_token(user, token)

    def list_users(self, org):
        return self.db.all(org)

    def list_orgs(self):
        return self.db.orgs()

    def user_roles(self, username):
        return self.db.user_roles(username)

    def create_org(self, orgname):
        return self.db.create_org(orgname)

    def activate_org(self, orgname):
        return self.db.toggle_org(orgname, 1)

    def deactivate_org(self, orgname):
        return self.db.toggle_org(orgname, 0)

    def create_user(self, username, password, email, org_name=None):
        if self.config.security.use_org and not org_name:
            return False, "Organization name is required"
        return self.db.create(username, password, email, org_name)

    def update_user(self, username, password=None, email=None):
        if self.config.security.use_org and not org_name:
            return False, "Organization name is required"
        return self.db.update(username,
                              password=password,
                              email=email)

    def remove_org(self, name):
        return self.db.remove_org(name)

    def remove_user(self, username):
        return self.db.remove(username)

    def add_role(self, username, node, role):
        return self.db.add_role(username, node, role)

    def remove_role(self, username, node):
        return self.db.remove_role(username, node)


class AuthDb(object):

    def __init__(self, db, use_org):
        self.use_org = use_org
        self.db = db

    def authenticate(self, username, password):
        try:
            user = self.db.query(User).join(
                Org).filter(
                    User.username == username, User.password == password,
                    Org.active == True).one()  # noqa
            if user:
                access_map = UserRules(username)
                access_map.org = user.org.name or DEFAULT_ORG
                for role in user.roles:
                    access_map.add_role(role.servers, role.as_user)
                return user.id, access_map
        except Exception, ex:
            LOG.exception(ex)
        return None, None

        LOG.info("Auth failed for user %s" % username)

    def validate(self, username, token):
        try:
            user = self.db.query(User).join(
                Org, Token).filter(
                    User.username == username, Token.value == token,
                    Org.active == True,  # noqa
                    Token.expires_at > datetime.now()).first()

            if user:
                access_map = UserRules(username)
                access_map.org = user.org.name or DEFAULT_ORG
                for role in user.roles:
                    access_map.add_role(role.servers, role.as_user)

                return user.id, access_map
        except Exception, ex:
            LOG.exception(ex)
        return None, None

    def all(self, org):
        users = self.db.query(User).join(
            Org).all()

        return [(u.username, u.email,
                 u.org.name, [g.name for g in u.groups]) for u in users]

    def orgs(self):
        orgs = [(org.name, org.uid, org.active)
                for org in self.db.query(Org).all()]
        return orgs

    def create_org(self, org_name):
        exists = self.db.query(self.db.query(Org).filter(
            Org.name == org_name).exists()).scalar()
        if exists:
            return False, "Organization already exists"

        try:
            org = Org(name=org_name)
            self.db.add(org)
            self.db.commit()
            return True, org.uid
        except Exception as exc:
            return False, "Cannot create organization, error: %r" % exc

    def create(self, username, password, email, org_name=None):
        exists = self.db.query(self.db.query(User).filter(
            User.username == username).exists()).scalar()
        if exists:
            return False, "User already exists"
        try:
            if org_name:
                org = self.db.query(Org).filter(Org.name == org_name).first()
                if not org:
                    return False, "Organization %s doesn't exist" % org_name
            else:
                org = self.db.query(Org).first()
                if not org:
                    return False, "Default Organization is not set"

            hash_pwd = hash_token(password)
            user = User(username=username,
                        password=hash_pwd,
                        email=email,
                        org=org)
            self.db.add(user)
            self.db.commit()
        except Exception, ex:
            return False, "Cannot create user: " + str(ex)
        return True, "Added"

    def update(self, username, **kwargs):
        email = kwargs.get('email')
        password = kwargs.get('password')
        if not email and not password:
            return False, "To update user, send either email or password"

        try:
            user = self.db.query(User).filter(
                User.username == username).first()
            if not user:
                return False, "User doesn't exist"

            user.email = email
            user.password = hash_token(password)
            self.db.add(user)
            self.db.commit()

        except Exception, exc:
            LOG.error(exc)
            return False, "Cannot update user"
        return True, "Updated"

    def remove_org(self, name):
        org = self.db.query(Org).filter(
            Org.name == name).first()
        if not org:
            return False, "Organization doesn't exist"
        try:
            self.db.delete(org)
            self.db.commit()
            return True, "Organization deleted"
        except Exception as exc:
            LOG.error(exc)
            self.db.rollback()
            return False, "Cannot delete organization"

    def toggle_org(self, name, new_status):
        org = self.db.query(Org).filter(
            Org.name == name).first()
        if not org:
            return False, "Organization doesn't exist"

        try:
            org.active = bool(new_status)
            self.db.add(org)
            self.db.commit()
        except Exception as exc:
            LOG.error(exc)
            self.db.rollback()
            return False, "Cannot toggle organization"
        return True, "Organization %s" % ('activated' if new_status else
                                          'deactivated')

    def remove(self, username):
        try:
            deleted = self.db.query(User).filter(
                User.username == username).delete()
            if not deleted:
                return False, "User doesn't exist"
            return True, "User deleted"
        except Exception, exc:
            LOG.error(exc)
            self.db.rollback()
            return False, "Error deleting user"
        return False, "User not found"

    def user_roles(self, username):
        roles = self.db.query(Role).join(User).filter(
            User.username == username).all()
        return dict([role.servers, role.as_user] for role in roles)

    def add_role(self, username, node, role):
        user = self.db.query(User).filter(User.username == username).first()
        if not user:
            return False, "User doesn't exist"
        # Test role
        if node != "*":
            try:
                re.compile(node)
            except re.error:
                return False, "%s is not a valid role/regex"
        try:
            exists = self.db.query(self.db.query(Role).join(User).filter(
                User.username == username,
                Role.servers == node,
                Role.as_user == role).exists()).scalar()

            if exists:
                return False, "Role already exists"

            role = Role(user_id=user.id, servers=node, as_user=role)
            self.db.add(role)
            self.db.commit()
            return True, "Role added"
        except Exception, exc:
            LOG.error(exc)
            self.db.rollback()
            return False, "Error adding role"
        return False, "User not found"

    def remove_role(self, username, node):
        try:
            user = self.db.query(User).filter(
                User.username == username).first()
            if not user:
                return False, "User doesn't exist"
            roles = self.db.query(Role).join(User).filter(
                User.username == username, Role.servers == node).all()
            if not roles:
                return False, "Role not found"
            for role in roles:
                self.db.delete(role)
            self.db.commit()
        except Exception, exc:
            LOG.error(exc)
            self.db.rollback()
            return False, "Not deleted"
        return True, "Role deleted"

    def get_token(self, username, expiry):
        """
        Create auth token, valid for the specified (expiry) minutes.
        If expiry == -1, then the token will not expire
        """
        try:
            user = self.db.query(User).join(Org).filter(
                User.username == username).first()
            if user:
                try:
                    expiry = int(expiry)
                    if expiry == -1:
                        # Max
                        expiry_date = datetime.max
                    else:
                        exp = int(expiry)
                        expiry_date = datetime.now() + timedelta(minutes=exp)
                except Exception, ex:
                    LOG.warn(ex)
                    expiry_date = datetime.now() + \
                        timedelta(minutes=DEFAULT_EXPIRE)

                _token = random_token(None)
                LOG.warn("token expires at: %s" % expiry_date)
                token = Token(expires_at=expiry_date, user_id=user.id,
                              value=_token)
                self.db.add(token)
                self.db.commit()

                LOG.info("Creating api token for user %s, "
                         "expires at %s" % (username, expiry_date))
                return (token.value, token.expires_at)
        except Exception, exc:
            LOG.error(exc)
            self.db.rollback()
        return (None, None)

    def invalidate_token(self, user, token):
        token = self.db.query(Token).join(User).filter(
            Token.value == token, User.username == user).first()
        if token:
            self.db.delete(token)
            return (True, "Token invalidated")
        else:
            return (False, "Token not found")


class UserRules(object):

    def __init__(self, owner):
        self.owner = owner
        self.rules = []
        self.default = None
        self.org = None

    def __repr__(self):
        return "%s:[%s]:%s" % (self.owner, self.default,
                               ';'.join([str(r[0].pattern) + ':' + r[1]
                                         for r in self.rules]))

    def add_role(self, node, role):
        if node == '*':
            self.default = role
        else:
            try:
                self.rules.append((re.compile(node, re.I), role))
            except re.error:
                LOG.error("Rule %s for user %s is invalid regex" % (
                    node, self.owner))

    def select(self, node):
        for rule, role in self.rules:
            if rule.match(node):
                LOG.info("Rule %s applied for user %s" % (node, self.owner))
                return role

        if self.default:
            LOG.info("Default rule %s applied for user %s" % (self.default,
                                                              self.owner))
            return self.default

        return None
