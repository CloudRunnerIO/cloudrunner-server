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

import os
import tempfile

from cloudrunner.util.crypto import hash_token
from cloudrunner.util.loader import local_plugin_loader
from cloudrunner_server.tests import base
from cloudrunner_server.plugins.auth.base import AuthPluginBase


class TestUsersWithoutOrg(base.BaseTestCase):

    def fixture(self):
        _, file_name = tempfile.mkstemp(suffix='.sql3')
        self.db = file_name
        db_url = "sqlite:///%s" % self.db
        base.CONFIG.users.db = db_url
        base.CONFIG.security.use_org = False
        local_plugin_loader(base.CONFIG.auth)
        self.auth = AuthPluginBase.__subclasses__()[0](base.CONFIG)
        self.auth.create_org('DEFAULT')
        self.auth.create_user("user1", "token1")

    def release(self):
        pass  # os.unlink(self.db)

    def test_login(self):
        self.assertEqual(len(AuthPluginBase.__subclasses__()), 1)
        success, access_map = self.auth.authenticate("user1", "token1")
        print success, access_map
        self.assertTrue(success, access_map)
        self.assertEquals(access_map.org, 'DEFAULT')

    def test_default_role(self):
        self.assertTrue(*self.auth.add_role('user1', '*', 'admin'))

    def test_duplicate_role(self):
        self.assertTrue(*self.auth.add_role('user1', '*', 'admin'))
        self.assertFalse(*self.auth.add_role('user1', '*', 'admin'))

        self.assertTrue(
            *self.auth.add_role('user1', r'.*\.cloudrunner', 'admin'))
        self.assertFalse(
            *self.auth.add_role('user1', r'.*\.cloudrunner', 'admin'))

        self.assertCount(self.auth.user_roles('user1'), 2)
        self.assertTrue(*self.auth.remove_role('user1', '*'))
        self.assertCount(self.auth.user_roles('user1'), 1)

    def test_wrong_role(self):
        self.assertFalse(*self.auth.add_role('user1', '?', 'admin'))

    def test_rm_role(self):
        self.assertTrue(*self.auth.add_role('user1', '*', 'admin'))
        self.assertTrue(*self.auth.remove_role('user1', '*'))

    def test_wrong_pass(self):
        self.assertFalse(*self.auth.authenticate("user1", "some bad token"))

    def test_bad_token(self):
        self.assertFalse(*self.auth.validate("user1", "some wrong token"))

    def test_rm_user(self):
        self.assertTrue(
            *self.auth.create_user('user2', 'token2'))
        success, access_map = self.auth.authenticate("user2",  "token2")
        self.assertTrue(success, access_map)
        self.assertEquals(access_map.org, 'DEFAULT')
        self.assertTrue(*self.auth.remove_user('user2'))
        self.assertFalse(*self.auth.authenticate("user2", "token2"))

    def test_create_token(self):
        user, token, org = self.auth.create_token("user1", expiry=1400)
        self.assertIsNotNone(token)
        success, access_map = self.auth.validate("user1", token)
        self.assertTrue(success, access_map)
        self.assertEquals(access_map.org, 'DEFAULT')


class TestUsersWithOrg(base.BaseTestCase):

    def fixture(self):
        _, file_name = tempfile.mkstemp()
        self.db = file_name
        db_url = "sqlite:///{}".format(self.db)
        base.CONFIG.users.db = db_url
        base.CONFIG.security.use_org = True
        local_plugin_loader(base.CONFIG.auth)
        self.auth = AuthPluginBase.__subclasses__()[0](base.CONFIG)
        success, self.org_uid = self.auth.create_org('MyOrg')
        self.auth.create_user("user1", "token1", 'MyOrg')

    def release(self):
        os.unlink(self.db)

    def test_login(self):
        self.assertEqual(len(AuthPluginBase.__subclasses__()), 1)
        success, access_map = self.auth.authenticate("user1", "token1")
        self.assertTrue(success, access_map)
        self.assertEquals(access_map.org, 'MyOrg')

    def test_default_role(self):
        self.assertTrue(*self.auth.add_role('user1', '*', 'admin'))

    def test_duplicate_role(self):
        self.assertTrue(*self.auth.add_role('user1', '*', 'admin'))
        self.assertFalse(*self.auth.add_role('user1', '*', 'admin'))

        self.assertTrue(
            *self.auth.add_role('user1', r'.*\.cloudrunner', 'admin'))
        self.assertFalse(
            *self.auth.add_role('user1', r'.*\.cloudrunner', 'admin'))

        self.assertCount(self.auth.user_roles('user1'), 2)
        self.assertTrue(*self.auth.remove_role('user1', '*'))
        self.assertCount(self.auth.user_roles('user1'), 1)

    def test_wrong_role(self):
        self.assertFalse(*self.auth.add_role('user1', '?', 'admin'))

    def test_rm_role(self):
        self.assertTrue(*self.auth.add_role('user1', '*', 'admin'))
        self.assertTrue(*self.auth.remove_role('user1', '*'))

    def test_wrong_pass(self):
        self.assertFalse(*self.auth.authenticate("user1", "some bad token"))

    def test_bad_token(self):
        self.assertFalse(*self.auth.validate("user1", "some wrong token"))

    def test_rm_user(self):
        self.assertTrue(
            *self.auth.create_user('user2', 'token2', 'MyOrg'))
        success, access_map = self.auth.authenticate("user2", "token2")
        self.assertTrue(success, access_map)
        self.assertEquals(access_map.org, 'MyOrg')
        self.assertTrue(*self.auth.remove_user('user2'))
        self.assertFalse(*self.auth.authenticate("user2", "token2"))

    def test_create_token(self):
        user, token, org = self.auth.create_token("user1", expiry=1400)
        self.assertIsNotNone(token)
        success, access_map = self.auth.validate("user1", token)
        self.assertTrue(success, access_map)
        self.assertEquals(access_map.org, 'MyOrg')

    def test_list_all(self):
        users = []
        for idx in range(10):
            username = 'user{}'.format(idx)
            self.auth.create_user(username, 'token', 'MyOrg')
            users.append((username, 'MyOrg'))

        res = self.auth.db.all()
        self.assertItemsEqual(users, res)

    def test_rm_org(self):
        status, msg = self.auth.db.remove_org('MyOrg')
        self.assertTrue(status)

        status, msg = self.auth.db.remove_org('YourOrg')
        self.assertFalse(status)
