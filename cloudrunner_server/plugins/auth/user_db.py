#!/usr/bin/python
# -*- coding: utf-8 -*-
# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2013 CloudRunner.IO
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import datetime
import logging
import random
import re
import string
import sqlite3
import uuid

from cloudrunner.core.message import DEFAULT_ORG
from cloudrunner.util.crypto import hash_token
from cloudrunner_server.plugins.auth.base import AuthPluginBase

TOKEN_LEN = 60
DEFAULT_EXPIRE = 1440  # 24h

LOG = logging.getLogger("UserMap")


class UserMap(AuthPluginBase):

    def __init__(self, config):
        self.config = config

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

    def create_token(self, user, password, expiry=None, **kwargs):
        return self.db.get_token(user, expiry or DEFAULT_EXPIRE)

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

    def __init__(self, db_path, use_org):
        try:
            self.use_org = use_org
            self.db = sqlite3.connect(db_path)
        except:
            LOG.error("Cannot connect to auth DB: %s" % db_path)
            return
        try:
            cur = self.db.cursor()
            users_count = cur.execute('SELECT count(*) FROM Users').fetchone()
        except:
            # Create tables
            LOG.warn("Database doesn't exist")
            cur.execute('CREATE TABLE Organizations (id integer primary key, '
                        'name text, org_uid text, active int)')
            cur.execute('CREATE TABLE Users (id integer primary key, '
                        'username text, token text, org_uid text)')
            cur.execute('CREATE TABLE AccessMap (user_id integer, '
                        'servers text, role text)')
            cur.execute('CREATE TABLE Tokens (user_id integer, '
                        'token text, expiry timestamp)')
            self.db.commit()
            self.create_org('DEFAULT')

    def authenticate(self, username, password):
        cur = self.db.cursor()
        user_data = cur.execute("SELECT Users.id FROM Users "
                                "INNER JOIN Organizations org "
                                "ON Users.org_uid = org.org_uid "
                                "WHERE username = ? AND token = ? "
                                "AND active = 1",
                                (username, password)).fetchone()
        if user_data:
            return user_data[0], username
        LOG.info("Auth failed for user %s" % username)

    def validate(self, username, token):
        cur = self.db.cursor()
        user_token = cur.execute("SELECT user_id FROM Tokens "
                                 "INNER JOIN Users "
                                 "ON Users.id = Tokens.user_id "
                                 "WHERE username = ? AND Tokens.token = ? "
                                 "AND expiry > ?",
                                (username, token,
                                    datetime.datetime.now())).fetchone()
        if user_token:
            return user_token[0], username
        LOG.info("Token validation failed for user %s" % username)

    def load(self, user_id, username, *args):
        cur = self.db.cursor()
        user_data = cur.execute("SELECT servers, role FROM AccessMap "
                                "WHERE user_id = ?", (user_id,))
        access_map = UserRules(username)

        for data in user_data.fetchall():
            access_map.add_role(data[0], data[1])

        org_data = cur.execute("SELECT org.name FROM Organizations org "
                               "INNER JOIN Users "
                               "ON org.org_uid = Users.org_uid "
                               "WHERE org.active = 1 and Users.id = ?",
                               (user_id,)).fetchone()
        if org_data and self.use_org:
            access_map.org = org_data[0]
        else:
            access_map.org = DEFAULT_ORG
        return access_map

    def all(self):
        cur = self.db.cursor()
        users_data = cur.execute("SELECT username, org.name FROM Users "
                                 "INNER JOIN Organizations org "
                                 "ON Users.org_uid = org.org_uid")
        users = [(user[0], user[1]) for user in users_data.fetchall()]
        return users

    def orgs(self):
        cur = self.db.cursor()
        org_data = cur.execute(
            "SELECT name, org_uid, active FROM Organizations")
        orgs = [(org[0], org[1], 'Active' if org[2] else 'Inactive')
                for org in org_data.fetchall()]
        return orgs

    def create_org(self, org_name):
        cur = self.db.cursor()
        cur.execute("SELECT * FROM Organizations WHERE name = ?", (org_name,))
        if cur.fetchone():
            return False, "Organization already exists"

        try:
            uid = str(uuid.uuid1())
            cur.execute(
                "INSERT INTO Organizations (name, org_uid, active) "
                "VALUES (?, ?, 1)",
                       (org_name, uid))
            self.db.commit()
        except:
            return False, "Cannot create organization"
        return True, uid

    def create(self, username, password, org_name):
        cur = self.db.cursor()
        cur.execute("SELECT * FROM Users WHERE username = ?", (username,))
        if cur.fetchone():
            return False, "User already exists"

        try:
            if org_name:
                org_id = cur.execute("SELECT org_uid from Organizations "
                                     "WHERE name = ?", (org_name,)).fetchone()
                if not org_id:
                    return False, "Organization %s doesn't exist" % org_name
            else:
                org_id = cur.execute("SELECT org_uid from Organizations "
                                     "LIMIT 1").fetchone()
                if not org_id:
                    return False, "Default Organization is not set"

            token = hash_token(password)
            cur.execute("INSERT INTO Users (username, token, org_uid) "
                        "VALUES (?, ?, ?)", (username, token, org_id[0]))
            self.db.commit()
        except Exception, ex:
            return False, "Cannot create user" + str(ex)
        return True, "Added"

    def remove_org(self, name):
        cur = self.db.cursor()
        cur.execute("DELETE FROM Organizations WHERE name = ?", (name,))
        self.db.commit()
        if cur.rowcount:
            return True, "Organization deleted"
        else:
            return False, "Organization not found"

    def toggle_org(self, name, new_status):
        cur = self.db.cursor()
        cur.execute("UPDATE Organizations SET active = ?", (new_status,))
        self.db.commit()
        if cur.rowcount:
            return True, "Organization %s" % ('activated' if new_status else
                                              'deactivated')
        else:
            return False, "Organization not found"

    def remove(self, username):
        cur = self.db.cursor()
        cur.execute("DELETE FROM Users WHERE username = ?", (username,))
        self.db.commit()
        if cur.rowcount:
            return True, "User deleted"
        else:
            return False, "User not found"

    def user_roles(self, username):
        cur = self.db.cursor()
        user_data = cur.execute("SELECT servers, role FROM AccessMap "
                                "INNER JOIN Users "
                                "ON Users.id = AccessMap.user_id "
                                "WHERE Users.username = ?", (username,))
        roles = {}
        for data in user_data.fetchall():
            roles[data[0]] = data[1]

        return roles

    def add_role(self, username, node, role):
        cur = self.db.cursor()
        user_data = cur.execute("SELECT id FROM Users WHERE username = ?",
                               (username,))
        user_id = user_data.fetchone()
        if user_id:
            user_id = user_id[0]
            # Test role
            if node != "*":
                try:
                    re.compile(node)
                except re.error:
                    return False, "%s is not a valid role/regex"

            if_exists = cur.execute("SELECT * FROM AccessMap "
                                    "WHERE user_id = ? AND servers = ?",
                                   (user_id, node))
            exists = if_exists.fetchone()
            if exists:
                return False, "Role already exists"

            cur.execute("INSERT INTO AccessMap VALUES(?, ?, ?)",
                       (user_id, node, role))
            self.db.commit()
            return True, "Role added"
        else:
            return False, "User not found"

    def remove_role(self, username, node):
        cur = self.db.cursor()
        user_data = cur.execute("SELECT id FROM Users WHERE username = ?",
                               (username,))
        user_id = user_data.fetchone()
        if user_id:
            user_id = user_id[0]
            cur.execute("DELETE FROM AccessMap "
                        "WHERE user_id = ? AND servers = ?",
                       (user_id, node))
            self.db.commit()
            if cur.rowcount:
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
        cur = self.db.cursor()
        user_c = cur.execute("SELECT id FROM Users WHERE username = ?",
                             (user,))
        user_id = user_c.fetchone()
        if user_id:
            user_id = user_id[0]
            if expiry == -1:
                # Max
                expiry_date = datetime.datetime.max
            else:
                expiry_date = datetime.datetime.now() + \
                    datetime.timedelta(minutes=expiry)
            # Purge old tokens
            cur.execute("DELETE FROM Tokens WHERE expiry < ?",
                        (datetime.datetime.now(),))
            cur.execute("INSERT INTO Tokens VALUES(?, ?, ?)",
                        (user_id, token, expiry_date))
            LOG.info("Creating api token for user %s, "
                     "expires at: %s" % (user, expiry))
            self.db.commit()
            return token


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
