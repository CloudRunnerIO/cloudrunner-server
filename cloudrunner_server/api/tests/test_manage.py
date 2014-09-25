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
import webtest


class TestManage(base.BaseRESTTestCase):

    def setUp(self):
        super(TestManage, self).setUp()
        self.redis.smembers.return_value = set(['is_admin', 'is_test_user'])

    def ztest_list_users(self):
        resp = self.app.get('/rest/manage/users/',
                            headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                     'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json

        self.assertEqual(resp_json['users'], [
            {
                "username": "testuser",
                "first_name": "User",
                "active": True,
                "last_name": "One",
                "created_at": "2014-08-01 00:00:00",
                "groups": None,
                "department": "Dept",
                "position": "Sr engineer",
                "email": "email"
            },
            {
                "username": "testuser2",
                "first_name": "User",
                "active": True,
                "last_name": "Second",
                "created_at": "2014-08-02 00:00:00",
                "groups": ["admin"],
                "department": "HR",
                "position": "HR manager",
                "email": "email"
            }], resp.body)

    def ztest_create_user(self):
        resp = self.app.post('/rest/manage/users',
                             "username=testuser3&email=email"
                             "&password=passX&org=MyOrg"
                             "&first_name=first&last_name=last"
                             "&department=dept&position=pos",
                             headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                      'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json

        self.assertEqual(resp_json, {"success": {"status": "ok"}}, resp.body)

        self.assertRedisInc('users:create')
        self.assertRedisPub('users:create', 3)

    def ztest_update_user(self):
        resp = self.app.put(
            '/rest/manage/users/',
            "username=testuser2&email=emailXY&password=newpass"
            "&first_name=first&last_name=last"
            "&department=dept&position=pos",
            headers={'Cr-Token': 'PREDEFINED_TOKEN',
                     'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json

        self.assertEqual(
            resp_json, {"success": {"status": "ok"}}, resp.body)

        self.assertRedisInc('users:modify')
        self.assertRedisPub('users:modify', 2)

    def ztest_update_user_fail(self):
        resp = self.app.put('/rest/manage/users/',
                            "username=nonexistinguser&email=emailXY"
                            "&first_name=name&last_name=emailXY"
                            "&department=dept&position=p"
                            "&password=newpass",
                            headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                     'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.body)
        resp_json = resp.json

        self.assertEqual(
            resp_json, {"error": {"msg": "User not found"}}, resp.body)

        self.assertRedisInc(None)
        self.assertRedisPub(None, None)

    def ztest_update_user_field_fail(self):

        resp = self.app.put('/rest/manage/users/',
                            "username=testuser2&password=newpass",
                            headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                     'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json

        self.assertEqual(
            resp_json, {"error": {"msg": "Field not present: 'email'",
                        "field": "'email'"}}, resp.body)

        self.assertRedisInc(None)
        self.assertRedisPub(None, None)

    def ztest_patch_user(self):
        resp = self.app.patch('/rest/manage/users/',
                              "username=testuser2&password=newpass",
                              headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                       'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json

        self.assertEqual(resp_json, {"success": {"status": "ok"}}, resp.body)

        self.assertRedisInc('users:modify')
        self.assertRedisPub('users:modify', 2)

    def ztest_patch_user_nothing(self):
        resp = self.app.patch('/rest/manage/users/',
                              "username=testuser2",
                              headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                       'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json

        self.assertEqual(
            resp_json, {"success": {"status": "ok"}}, resp.body)

    def ztest_delete_user(self):
        resp = self.app.delete('/rest/manage/users/testuser2',
                               headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                        'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json

        self.assertEqual(
            resp_json, {"success": {"status": "ok"}}, resp.body)

        self.assertRedisInc('users:delete')
        self.assertRedisPub('users:delete', 2)

    def ztest_delete_user_fail(self):
        resp = self.app.delete('/rest/manage/users/nonexistinguser',
                               headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                        'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json

        self.assertEqual(
            resp_json, {"error": {"msg": "User not found"}}, resp.body)

        self.assertRedisInc(None)
        self.assertRedisPub(None, None)

    # Groups

    def ztest_create_group(self):
        resp = self.app.post('/rest/manage/groups',
                             "name=new_group",
                             headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                      'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json

        self.assertEqual(resp_json, {"success": {"status": "ok"}}, resp.body)

    def ztest_modify_group(self):
        resp = self.app.put('/rest/manage/groups/',
                            "name=admin"
                            "&remove=root@production"
                            "&add=user1@x12&add=user2@x12"
                            "&add=user3@x23&add=user4@x23",
                            headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                     'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json

        self.assertEqual(resp_json, {"success": {"status": "ok"}}, resp.body)

        resp = self.app.get('/rest/manage/groups/admin',
                            headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                     'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json
        self.assertEqual(resp_json, {"group": {
            "name": "admin",
            "roles":
            [
                {"as_user": "user1", "servers": "x12"
                 },
                {"as_user": "user2", "servers": "x12"
                 },
                {"as_user": "user3", "servers": "x23"
                 },
                {"as_user": "user4", "servers": "x23"
                 }
            ]
        }}, resp.body)

    def ztest_delete_group(self):
        resp = self.app.delete('/rest/manage/groups/admin',
                               headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                        'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json

        self.assertEqual(
            resp_json, {"success": {"status": "ok"}}, resp.body)

    def ztest_delete_group_fail(self):
        resp = self.app.delete('/rest/manage/groups/nongroup',
                               headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                        'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json

        self.assertEqual(
            resp_json, {"error": {"msg": "Group not found"}}, resp.body)

    # Roles
    def ztest_list_roles(self):
        resp = self.app.get('/rest/manage/roles/testuser',
                            headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                     'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json

        self.assertEqual(
            sorted(resp_json['roles']),
            sorted([
                {"as_user": "root", "group": None, "servers": "*"},
                {"as_user": "guest", "group": None, "servers": "prod.*"},
                {"as_user": "developer", "group": None, "servers": "stg.*"}
            ]))

    def ztest_add_roles(self):
        resp = self.app.post('/rest/manage/roles/testuser2',
                             "servers=server3&as_user=ec2-user",
                             headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                      'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json

        self.assertEqual(resp_json, {"success": {"status": "ok"}},
                         resp.body)

    def ztest_rm_roles(self):
        self.assertEqual(
            len(self.app.get("/rest/manage/roles/testuser2",
                             headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                      'Cr-User': 'testuser'
                                      }).json['roles']), 2)
        resp = self.app.delete('/rest/manage/roles/testuser2/developer/stg.*',
                               headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                        'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json

        self.assertEqual(
            len(self.app.get("/rest/manage/roles/testuser2",
                             headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                      'Cr-User': 'testuser'}
                             ).json['roles']), 1)
        self.assertEqual(resp_json, {"success": {"status": "ok"}},
                         resp.body)

    def ztest_list_orgs_no_perm(self):
        self.assertRaises(webtest.app.AppError,
                          self.app.get, '/rest/manage/orgs/',
                          headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                   'Cr-User': 'testuser'})


class SuperAdminTest(base.BaseRESTTestCase):

    def setUp(self):
        super(SuperAdminTest, self).setUp()
        self.redis.smembers.return_value = set(['is_super_admin'])

    def ztest_list_orgs(self):
        resp = self.app.get('/rest/manage/orgs/',
                            headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                     'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200)
        resp_json = resp.json

        for org in resp_json['orgs']:
            org.pop('created_at')
            uuid = org.pop('uid')
            self.assertEqual(len(uuid), 32)
        self.assertContains(resp_json['orgs'],
                            {"active": True,
                             "name": "MyOrg"})
        self.assertContains(resp_json['orgs'],
                            {"active": False,
                             "name": "MyOrg2"})

    def ztest_create_org(self):
        resp = self.app.post('/rest/manage/orgs',
                             "org=OrgZ",
                             headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                      'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json

        self.assertEqual(resp_json, {"success": {"status": "ok"}}, resp.body)

    def ztest_activate_org(self):
        resp = self.app.patch('/rest/manage/orgs/MyOrg2',
                              'status=1',
                              headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                       'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json

        self.assertEqual(resp_json, {"success": {"status": "ok"}},
                         resp.body)

    def ztest_deactivate_org(self):
        resp = self.app.patch('/rest/manage/orgs/MyOrg2',
                              'status=0',
                              headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                       'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json

        self.assertEqual(resp_json, {"success": {"status": "ok"}},
                         resp.body)

    def test_delete_org(self):
        resp = self.app.delete('/rest/manage/orgs/MyOrg2',
                               headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                        'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json

        self.assertEqual(resp_json, {"success": {"status": "ok"}},
                         resp.body)
