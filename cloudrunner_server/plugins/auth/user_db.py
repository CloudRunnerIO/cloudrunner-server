#!/usr/bin/python
# -*- coding: utf-8 -*-
# vim: tabstop=4 shiftwidth=4 softtabstop=4

# /*******************************************************
#  * Copyright (C) 2013-2014 CloudRunner.io <info@cloudrunner.io>
#  *
#  * Proprietary and confidential
#  * This file is part of CloudRunner Server.
#  *
#  * CloudRunner Server can not be copied and/or distributed without the express
#  * permission of CloudRunner.io
#  *******************************************************/

import datetime
import logging
import random
import re
import string
import sqlite3
import uuid
from cloudrunner_server.db import get_db
from cloudrunner_server.db.columns import Column

from cloudrunner.core.message import DEFAULT_ORG
from cloudrunner.util.crypto import hash_token
from cloudrunner_server.plugins.auth.base import AuthPluginBase

TOKEN_LEN = 60
DEFAULT_EXPIRE = 1440  # 24h

LOG = logging.getLogger("UserMap")


class UserMap(AuthPluginBase):

    def __init__(self, config):
        self.config = config
        assert self.db

    @property
    def db(self):
        return AuthDb(self.config.users.db, self.config.security.use_org)

    def authenticate(self, user, password):
        """
        Authenticate using password
        """
        pwd_hash = hash_token(password)
        try:
            auth = self.db.authenticate(user, pwd_hash)
            if auth:
                return (True, self.db.load(*auth))
            return (False, None)
        except Exception, ex:
            LOG.exception(ex)
            return (False, None)

    def validate(self, user, token):
        """
        Authenticate using issued auth token
        """
        try:
            auth = self.db.validate(user, token)
            if auth:
                return (True, self.db.load(*auth))
            return (False, None)
        except Exception, ex:
            LOG.exception(ex)
            return (False, None)

    def create_token(self, user, password, **kwargs):
        return self.db.get_token(user,
                                 expiry=kwargs.get('expiry', DEFAULT_EXPIRE))

    def list_users(self):
        return self.db.all()

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

    def create_user(self, username, password, org_name=None):
        if self.config.security.use_org and not org_name:
            return False, "Organization name is required"
        return self.db.create(username, password, org_name)

    def remove_org(self, name):
        return self.db.remove_org(name)

    def remove_user(self, username):
        return self.db.remove(username)

    def add_role(self, username, node, role):
        return self.db.add_role(username, node, role)

    def remove_role(self, username, node):
        return self.db.remove_role(username, node)


class AuthDb(object):
    SCHEMA = {
        "organizations": {
            "id": Column('id', primary_key=True, null=False),
            "name": Column('string', length=80),
            "org_uid": Column('text'),
            "active": Column('boolean', default=1),
        },
        "users": {
            "id": Column('id', primary_key=True, null=False),
            "username": Column('string', length=80),
            "token": Column('text'),
            "org_uid": Column('text'),
            "role": Column('text'),
        },
        "access_map": {
            "user_id": Column('integer'),
            "servers": Column('text'),
            "role": Column('string', length=120),
        },
        "user_tokens": {
            "user_id": Column('integer'),
            "token": Column('text'),
            "expiry": Column('timestamp'),
        }

    }

    def __init__(self, db_path, use_org):
        try:
            self.use_org = use_org
            self.dbm = get_db(db_path)
        except:
            LOG.error("Cannot connect to auth DB: %s" % db_path)
            raise
        self.dbm.define_schema(self.SCHEMA)

        def on_create(table_name):
            if not self.use_org and table_name == 'organizations':
                # Create initial Default record for single-tenant
                self.create_org('DEFAULT')
        self.dbm.create_tables(create_callback=on_create)

    def authenticate(self, username, password):
        res = self.dbm.db.select(
            ['users', 'organizations org'],
            what='users.id',
            where='users.org_uid = org.org_uid '
                  'AND username = $username '
                  'AND token = $token '
                  'AND org.active = 1',
            vars={'username': username, 'token': password},
        )

        user_data = list(res)
        if user_data:
            return user_data[0].id, username

        LOG.info("Auth failed for user %s" % username)

    def validate(self, username, token):
        user_token = self.dbm.db.select(
            ['user_tokens', 'users'],
            where="users.id = user_tokens.user_id"
                  " AND username=$username"
                  " AND user_tokens.token=$token"
                  " AND expiry > date('now')",
            vars={
                "username": username,
                "token": token
            },
            what="user_id"
        )

        user_token = list(user_token)

        if user_token:
            return user_token[0].user_id, username
        LOG.info("Token validation failed for user %s" % username)

    def load(self, user_id, username, *args):
        user_data = self.dbm.access_map.select(
            what='servers, role',
            where='user_id = $user_id',
            vars=dict(user_id=user_id)
        )
        access_map = UserRules(username)
        for data in user_data:
            access_map.add_role(data.servers, data.role)

        org_data = self.dbm.db.select(
            ['organizations org', 'users'],
            where='org.org_uid = users.org_uid'
                  ' AND org.active = 1'
                  ' AND users.id=$user_id',
            vars=dict(user_id=user_id),
            what='org.name'
        )
        org_data = list(org_data)
        if org_data and self.use_org:
            access_map.org = org_data[0].name
        else:
            access_map.org = DEFAULT_ORG
        return access_map

    def all(self):
        users = self.dbm.db.select(
            ['users', 'organizations org'],
            where='users.org_uid=org.org_uid',
            what='username, org.name as org_name'
        )
        return [(u.username, u.org_name) for u in users]

    def orgs(self):

        org_data = self.dbm.organizations.select(
            what="name, org_uid, active",
        )
        orgs = [(org.name, org.org_uid, 'Active' if org.active else 'Inactive')
                for org in org_data]
        return orgs

    def create_org(self, org_name):

        if list(self.dbm.organizations.select(where="name=$name",
                                              vars={"name": org_name})):
            return False, "Organization already exists"

        try:
            uid = str(uuid.uuid4())
            self.dbm.organizations.insert(name=org_name, org_uid=uid)
        except Exception as exc:
            return False, "Cannot create organization, error: %r" % exc
        return True, uid

    def create(self, username, password, org_name=None):
        users = self.dbm.users.select(where="username = $username",
                                      vars={"username": username})
        if list(users):
            return False, "User already exists"

        try:
            if org_name:
                org_id = self.dbm.organizations.select(
                    what='org_uid',
                    where='name=$org_name',
                    vars={"org_name": org_name})
                org_id = list(org_id)
                if not org_id:
                    return False, "Organization %s doesn't exist" % org_name
            else:
                org_id = self.dbm.organizations.select(
                    what='org_uid', limit=1)
                org_id = list(org_id)
                if not org_id and self.use_org:
                    return False, "Default Organization is not set"

            token = hash_token(password)
            if org_id:
                org_uid = org_id[0].org_uid
            else:
                org_uid = DEFAULT_ORG
            self.dbm.users.insert(username=username, token=token,
                                  org_uid=org_uid)
        except Exception, ex:
            return False, "Cannot create user" + str(ex)
        return True, "Added"

    def remove_org(self, name):
        res = self.dbm.organizations.delete(where="name=$name",
                                            vars=dict(name=name))
        if res:
            return True, "Organization deleted"
        else:
            return False, "Organization not found"

    def toggle_org(self, name, new_status):
        res = self.dbm.organizations.update(
            active=new_status,
            where="name=$name",
            vars={"name": name}
        )

        if res:
            return True, "Organization %s" % ('activated' if new_status else
                                              'deactivated')
        else:
            return False, "Organization not found"

    def remove(self, username):
        res = self.dbm.users.delete(where="username=$username",
                                    vars={"username": username})

        if res:
            return True, "User deleted"
        else:
            return False, "User not found"

    def get_user_id(self, username):
        user_data = self.dbm.users.select(
            what="id",
            where="username = $username",
            vars=dict(username=username)
        )

        user_data = list(user_data)
        if user_data:
            return user_data[0].id

    def user_roles(self, username):
        user_data = self.dbm.db.select(
            ['access_map as am', 'users'],
            what="am.servers, am.role",
            where="users.id = am.user_id "
                  "AND users.username = $username",
            vars={"username": username},
        )
        roles = {}
        for data in user_data:
            roles[data.servers] = data.role

        return roles

    def add_role(self, username, node, role):
        user_id = self.get_user_id(username)
        if user_id:
            # Test role
            if node != "*":
                try:
                    re.compile(node)
                except re.error:
                    return False, "%s is not a valid role/regex"

            exists = self.dbm.access_map.select(
                where="user_id=$user_id AND servers=$servers",
                vars=dict(user_id=user_id, servers=node)
            )
            if list(exists):
                return False, "Role already exists"

            self.dbm.access_map.insert(
                user_id=user_id, servers=node, role=role)
            return True, "Role added"
        else:
            return False, "User not found"

    def remove_role(self, username, node):
        user_id = self.get_user_id(username)
        if user_id:
            deleted = self.dbm.access_map.delete(
                where="user_id=$user_id AND servers=$servers",
                vars=dict(user_id=user_id, servers=node)
            )
            if deleted:
                return True, "Role deleted"
            else:
                return False, "Role not found"
        else:
            return False, "User not found"

    def get_token(self, user, expiry):
        """
        Create auth token, valid for the specified (expiry) minutes.
        If expiry == -1, then the token will not expire
        """
        token = ''.join(random.choice(string.printable[:-6])
                        for x in range(TOKEN_LEN))

        user_id = self.get_user_id(user)
        org_data = self.dbm.db.select(
            ['organizations org', 'users'],
            where='org.org_uid = users.org_uid'
                  ' AND org.active = 1'
                  ' AND users.id=$user_id',
            vars=dict(user_id=user_id),
            what='org.name'
        )
        org_data = list(org_data)
        if org_data and self.use_org:
            org = org_data[0].name
        else:
            org = None

        if user_id:
            if expiry == -1:
                # Max
                expiry_date = datetime.datetime.max
            else:
                expiry_date = datetime.datetime.now() + \
                    datetime.timedelta(minutes=expiry)
            # Purge old tokens
            self.dbm.user_tokens.delete(where="expiry < date('now')")
            self.dbm.user_tokens.insert(
                user_id=user_id,
                token=token,
                expiry=expiry_date
            )
            LOG.info("Creating api token for user %s, "
                     "expires at %s" % (user, expiry_date))
            return user, token, org
        return (None, None, None)


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
                LOG.error("Rule %s for user %s is invalid regex" % (node,
                                                                    self.owner))

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
