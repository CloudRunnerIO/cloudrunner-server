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

from cloudrunner.util.loader import local_plugin_loader
from cloudrunner_server.tests import base
from cloudrunner_server.plugins.auth.base import AuthPluginBase


class TestUsersWithoutOrg(base.BaseTestCase):

    def setUp(self):
        base.CONFIG.security.use_org = False
        local_plugin_loader(base.CONFIG.auth)
        self.auth = AuthPluginBase.__subclasses__()[0](base.CONFIG)
        self.auth.set_context_from_config(recreate=True, autocommit=False)
        self.populate_defaults()

    def populate_defaults(self):
        self.auth.create_org("DEFAULT")
        self.auth.activate_org("DEFAULT")
        self.auth.create_user("user1", "token1", "email1@site.com")

    def test_login(self):
        self.assertEqual(len(AuthPluginBase.__subclasses__()), 1)
        success, access_map = self.auth.authenticate("user1", "token1")
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
            *self.auth.create_user('user2', 'token2', "email2@site.com"))
        success, access_map = self.auth.authenticate("user2", "token2")
        self.assertTrue(success, access_map)
        self.assertEquals(access_map.org, 'DEFAULT')
        self.assertTrue(*self.auth.remove_user('user2'))
        self.assertFalse(*self.auth.authenticate("user2", "token2"))

    def test_create_token(self):
        token, expires_at = self.auth.create_token("user1", "token2",
                                                   expiry=1400)
        self.assertIsNotNone(token)
        success, access_map = self.auth.validate("user1", token)
        self.assertTrue(success, access_map)
        self.assertEquals(access_map.org, 'DEFAULT')


class TestUsersWithOrg(base.BaseTestCase):

    def fixture(self):
        base.CONFIG.security.use_org = True
        local_plugin_loader(base.CONFIG.auth)
        self.auth = AuthPluginBase.__subclasses__()[0](base.CONFIG)
        self.auth.set_context_from_config(recreate=True, autocommit=False)
        self.populate_defaults()

    def populate_defaults(self):
        success, self.org_uid = self.auth.create_org('MyOrg')
        self.auth.activate_org('MyOrg')
        self.auth.create_user("user1", "token1", "email1@site.com",
                              org_name='MyOrg')

    def test_login(self):
        self.assertEqual(len(AuthPluginBase.__subclasses__()), 1)
        success, access_map = self.auth.authenticate("user1", "token1")
        self.assertTrue(success, access_map)
        self.assertCount(self.auth.list_orgs(), 1)
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
            *self.auth.create_user('user2', 'token2', 'email2@site.com',
                                   org_name='MyOrg'))
        success, access_map = self.auth.authenticate("user2", "token2")
        self.assertTrue(success, access_map)
        self.assertEquals(access_map.org, 'MyOrg')
        self.assertTrue(*self.auth.remove_user('user2'))
        self.assertFalse(*self.auth.authenticate("user2", "token2"))

    def test_create_token(self):
        token, expires_at = self.auth.create_token("user1", "token2",
                                                   expiry=1400)
        self.assertIsNotNone(token)
        success, access_map = self.auth.validate("user1", token)
        self.assertTrue(success, access_map)
        self.assertEquals(access_map.org, 'MyOrg')

    def test_list_all(self):
        users = [("user1", "email1@site.com", "MyOrg")]
        for idx in range(10, 20):
            username = 'user%s' % (idx)
            self.auth.create_user(
                username, 'token', 'email3@site.com', org_name='MyOrg')
            users.append((username, 'email3@site.com', 'MyOrg'))

        res = self.auth.db.all('MyOrg')
        self.maxDiff = None
        self.assertItemsEqual(users, res)

    def test_rm_org(self):
        status, msg = self.auth.db.remove_org('MyOrg')
        self.assertTrue(status)

        status, msg = self.auth.db.remove_org('YourOrg')
        self.assertFalse(status)
