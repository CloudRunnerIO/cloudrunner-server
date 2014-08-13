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

from cloudrunner_server.api.tests import base


class TestManage(base.BaseRESTTestCase):

    def test_list_users(self):
        resp = self.app.get('/rest/manage/users',
                            headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                     'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json

        self.assertEqual(resp_json['users'],
                         [{"org": "MyOrg",
                           "email": "email",
                           "groups": [],
                           "name": "testuser"},
                          {"org": "MyOrg",
                           "email": "email",
                           "groups": ["admin"],
                           "name": "testuser2"}], resp.body)

    def test_create_user(self):
        resp = self.app.post('/rest/manage/users',
                             "username=userXY&email=emailX"
                             "&password=passX&org=MyOrg",
                             headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                      'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json

        self.assertEqual(resp_json, {'status': "ok"}, resp.body)

        self.assertRedisInc('manage.users')
        self.assertRedisPub('manage.users', 'create')

    def test_update_user(self):
        resp = self.app.put(
            '/rest/manage/users',
            "username=testuser2&email=emailXY&password=newpass",
            headers={'Cr-Token': 'PREDEFINED_TOKEN',
                     'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json

        self.assertEqual(
            resp_json, {'status': "ok"}, resp.body)

        self.assertRedisInc('manage.users')
        self.assertRedisPub('manage.users', 'update')

    def test_update_user_fail(self):
        resp = self.app.put('/rest/manage/users',
                            "username=nonexistinguser&email=emailXY"
                            "&password=newpass",
                            headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                     'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json

        self.assertEqual(
            resp_json, {'error': "User doesn't exist"}, resp.body)

        self.assertRedisInc(None)
        self.assertRedisPub(None, None)

    def test_update_user_field_fail(self):

        resp = self.app.put('/rest/manage/users',
                            "username=testuser2&password=newpass",
                            headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                     'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json

        self.assertEqual(
            resp_json, {"error": "Missing value: 'email'"}, resp.body)

        self.assertRedisInc(None)
        self.assertRedisPub(None, None)

    def test_patch_user(self):
        resp = self.app.patch('/rest/manage/users',
                              "username=testuser2&password=newpass",
                              headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                       'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json

        self.assertEqual(
            resp_json, {"status": "ok"}, resp.body)

        self.assertRedisInc('manage.users')
        self.assertRedisPub('manage.users', 'update')

    def test_patch_user_fail(self):
        resp = self.app.patch('/rest/manage/users',
                              "username=testuser2",
                              headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                       'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json

        self.assertEqual(
            resp_json, {"error": "Nothing to update"}, resp.body)

        self.assertRedisInc(None)
        self.assertRedisPub(None, None)

    def test_delete_user(self):
        resp = self.app.delete('/rest/manage/users/testuser2',
                               headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                        'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json

        self.assertEqual(
            resp_json, {"status": "ok"}, resp.body)

        self.assertRedisInc('manage.users')
        self.assertRedisPub('manage.users', 'delete')

    def test_delete_user_fail(self):
        resp = self.app.delete('/rest/manage/users/nonexistinguser',
                               headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                        'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json

        self.assertEqual(
            resp_json, {"error": "User doesn't exist"}, resp.body)

        self.assertRedisInc(None)
        self.assertRedisPub(None, None)

    # Roles
    def test_list_roles(self):
        resp = self.app.get('/rest/manage/roles/testuser',
                            headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                     'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json

        self.assertEqual(resp_json['roles'],
                         [
                         {"node": "*", "as_user": "root"},
                         {"node": "prod.*", "as_user": "guest"},
                         {"node": "stg.*", "as_user": "developer"}
                         ],
                         resp.body)

    def test_add_roles(self):
        resp = self.app.post('/rest/manage/roles/testuser2',
                             "node=server3&role=ec2-user",
                             headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                      'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json

        self.assertRedisInc('manage.roles')
        self.assertRedisPub('manage.roles', 'create')

        self.assertEqual(resp_json, {"status": "ok"},
                         resp.body)

    def test_rm_roles(self):
        resp = self.app.delete('/rest/manage/roles/testuser2/stg.*',
                               headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                        'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json

        self.assertEqual(resp_json, {"status": "ok"},
                         resp.body)

        self.assertRedisInc('manage.roles')
        self.assertRedisPub('manage.roles', 'delete')

    def test_list_orgs(self):
        resp = self.app.get('/rest/manage/orgs',
                            headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                     'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json

        for org in resp_json['orgs']:
            uuid = org.pop('id')
            self.assertEqual(len(uuid), 32)
        self.assertContains(resp_json['orgs'],
                            {"active": True,
                             "name": "MyOrg"})
        self.assertContains(resp_json['orgs'],
                            {"active": False,
                             "name": "MyOrg2"})

    def test_create_org(self):
        resp = self.app.post('/rest/manage/orgs',
                             "org=OrgZ",
                             headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                      'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json

        self.assertEqual(resp_json, {'status': 'ok'}, resp.body)

        self.assertRedisInc('manage.orgs')
        self.assertRedisPub('manage.orgs', 'create')

    def test_activate_org(self):
        resp = self.app.patch('/rest/manage/orgs/MyOrg2',
                              'action=1',
                              headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                       'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json

        self.assertEqual(resp_json, {'status': 'ok'},
                         resp.body)

        self.assertRedisInc('manage.orgs')
        self.assertRedisPub('manage.orgs', 'update')

    def test_deactivate_org(self):
        resp = self.app.patch('/rest/manage/orgs/MyOrg2',
                              'action=0',
                              headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                       'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json

        self.assertEqual(resp_json, {'status': 'ok'},
                         resp.body)

        self.assertRedisInc('manage.orgs')
        self.assertRedisPub('manage.orgs', 'update')

    def test_delete_org(self):
        resp = self.app.delete('/rest/manage/orgs/MyOrg2',
                               headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                        'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json

        self.assertRedisInc('manage.orgs')
        self.assertRedisPub('manage.orgs', 'delete')

        self.assertEqual(resp_json, {'status': 'ok'},
                         resp.body)
