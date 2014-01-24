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

from cloudrunner_server.plugins.auth.base import AuthPluginBase
from keystoneclient.v2_0 import client

DEFAULT_EXPIRE = 1440  # 24h

LOG = logging.getLogger("KeystoneAuth")


class KeystoneAuth(AuthPluginBase):

    def __init__(self, config):
        self.config = config
        self.AUTH_URL = config.auth_url

    def authenticate(self, user, password):
        """
        Authenticate using password
        """
        try:
            keystone = client.Client(username=user, password=password,
                                     auth_url=self.AUTH_URL)
            if keystone.authenticate():
                return (True, self._load_tenants(keystone, user, password))
            return (False, None)
        except Exception, ex:
            LOG.exception(ex)
            return (False, None)

    def _load_tenants(self, keystone, username, password):
        tenants = keystone.tenants.list()
        access_map = UserRules(username)

        access_map.add_role('*', 'root')

        access_map.org = tenants[0].name
        access_map.organizations = [tenant.name for tenant in tenants]
        return access_map

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
        try:
            keystone = client.Client(username=user, password=password,
                                     auth_url=self.AUTH_URL)
            if keystone.authenticate():
                token = keystone.tokens.authenticate(
                    username=user, password=password)
                return token.token['id']
        except:
            return None

    def list_users(self):
        return self.db.all()

    def list_orgs(self):
        return self.db.orgs()

    def user_roles(self, username):
        return self.db.user_roles(username)

    def create_org(self, orgname):
        raise NotImplemented()

    def activate_org(self, orgname):
        raise NotImplemented()

    def deactivate_org(self, orgname):
        raise NotImplemented()

    def create_user(self, username, password, org_name=None):
        raise NotImplemented()

    def remove_org(self, name):
        raise NotImplemented()

    def remove_user(self, username):
        raise NotImplemented()

    def add_role(self, username, node, role):
        raise NotImplemented()

    def remove_role(self, username, node):
        raise NotImplemented()


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
