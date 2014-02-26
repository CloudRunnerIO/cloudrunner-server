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

from datetime import datetime
from datetime import timedelta
import logging
import random
import re
import string
import sqlite3
from time import mktime
from time import gmtime
import uuid

from cloudrunner_server.plugins.auth.base import AuthPluginBase

# try:
#    from keystoneclient.v3 import client
# except ImportError:
from keystoneclient.v2_0 import client
VERSION = 2
DEFAULT_EXPIRE = 1440  # 24h

LOG = logging.getLogger("KeystoneAuth")


class KeystoneAuth(AuthPluginBase):

    def __init__(self, config):
        self.config = config
        self.AUTH_URL = config.auth_url
        self.ADMIN_AUTH_URL = config.auth_admin_url
        self.admin_user = config.auth_user
        self.admin_pass = config.auth_pass
        self.admin_tenant = config.auth_admin_tenant or 'admin'
        self.timeout = int(config.auth_timeout or 5)
        self._token_cache = {}
        LOG.info("Keystone Auth with %s" % self.AUTH_URL)

    def authenticate(self, user, password):
        """
        Authenticate using password
        """
        try:
            keystone = client.Client(username=user, password=password,
                                     auth_url=self.AUTH_URL,
                                     timeout=self.timeout)
            if keystone.authenticate():
                tenant_map = self._load_tenant_map(keystone, user, password)
                return (True, tenant_map)
            return (False, None)
        except client.exceptions.Unauthorized:
            LOG.warn("Invalid login from %s" % user)
        except Exception, ex:
            LOG.exception(ex)

        return (False, None)

    def _get_tenants(self, client):
        if VERSION == 3:
            return client.projects
        else:
            return client.tenants

    def _load_tenant_map(self, keystone, username, password):
        tenants = self._get_tenants(keystone).list()
        access_map = UserRules(username)

        access_map.add_role('*', '@')

        access_map.org = tenants[0].name
        access_map.organizations = [tenant.name for tenant in tenants
                                    if tenant.enabled]
        return access_map

    def validate(self, user, token):
        """
        Authenticate using issued auth token
        """
        try:
            keystone = client.Client(username=user, token=token,
                                     auth_url=self.AUTH_URL,
                                     timeout=self.timeout)
            if keystone.authenticate():
                tenant_map = self._load_tenant_map(keystone, user, token)
                return (True, tenant_map)
            return (False, None)
        except client.exceptions.Unauthorized:
            LOG.warn("Invalid login from %s" % user)
        except Exception, ex:
            LOG.exception(ex)

        return (False, None)

    def create_token(self, user, password, expiry=None, **kwargs):
        # create new token from token
        auth_kwargs = dict(username=user)
        if kwargs.get('is_token'):
            auth_kwargs['token'] = password
        else:
            auth_kwargs['password'] = password
        try:
            keystone = client.Client(auth_url=self.AUTH_URL,
                                     timeout=self.timeout, **auth_kwargs)
            if keystone.authenticate():
                tenant_map = self._load_tenant_map(keystone, user, password)
                token = keystone.tokens.authenticate(**auth_kwargs)
                return user, token.token['id'], tenant_map.org
        except Exception, ex:
            LOG.error(ex)
            LOG.error(user)
            LOG.error(password)
            return (None, None, None)

    def list_users(self):
        return []

    def _admin_token(self):
        if 'admin_token' not in self._token_cache or \
            self._token_cache.get('admin_token', [0])[0] > gmtime():
            # Create token
            keystone = client.Client(tenant_name=self.admin_tenant,
                                     username=self.admin_user,
                                     password=self.admin_pass,
                                     auth_url=self.ADMIN_AUTH_URL,
                                     timeout=self.timeout)
            token = keystone.tokens.authenticate(username=self.admin_user,
                                                 password=self.admin_pass)
            if token.expires.endswith('Z'):
                _exp = token.expires[:-1]
                dt = datetime.strptime(_exp, "%Y-%m-%dT%H:%M:%S")
            else:
                # has time zone
                token.expires = token.expires[:-1]
                try:
                    dt = datetime.strptime(
                        token.expires, "%Y-%m-%dT%H:%M:%S%Z")
                except:
                    dt = datetime.strptime(
                        token.expires, "%Y-%m-%dT%H:%M:%S%z")

            # remove 5 sec to avoid time diffs
            dt -= timedelta(seconds=5)
            self._token_cache['admin_token'] = (mktime(dt.utctimetuple()),
                                                token.id)
        return self._token_cache['admin_token'][1]

    def list_orgs(self):
        admin_token = self._admin_token()
        c = client.Client(token=admin_token, auth_url=self.ADMIN_AUTH_URL,
                          tenant_name=self.admin_tenant, timeout=self.timeout)
        tenants_list = c.tenants.list()
        tenants = [tenant.name for tenant in tenants_list
                   if tenant.enabled]
        return tenants

    def user_roles(self, username):
        raise NotImplemented()

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
