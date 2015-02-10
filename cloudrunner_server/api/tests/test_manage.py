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

from copy import copy
from datetime import datetime
import webtest

from cloudrunner_server.api.tests import base

USERS = [{
    'username': 'testuser',
    'first_name': 'User',
    'last_name': 'One',
    'created_at': '2014-08-01 00:00:00',
    'enabled': True,
    'phone': None,
    'groups': None,
    'department': 'Dept',
    'position': 'Sr engineer',
    'email': 'user1@domain.com'
}, {
    'username': 'testuser3',
    'first_name': 'User',
    'last_name': 'Second',
    'created_at': '2014-08-02 00:00:00',
    'enabled': True,
    'phone': "555-666-7777",
    'groups': None,
    'department': 'HR',
    'position': 'HR manager',
    'email': 'user3@domain.com'}]


class TestManage(base.BaseRESTTestCase):

    def test_list_users(self, users=None):
        resp = self.app.get('/rest/manage/users/',
                            headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                     'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json
        _users = users or USERS
        self.assertEqual(resp_json['users'], _users)

    def test_create_user(self):
        resp = self.app.post('/rest/manage/users',
                             "username=testuser4&email=email"
                             "&password=passX&org=MyOrg&phone=555-555-5555"
                             "&first_name=first&last_name=last"
                             "&department=dept&position=pos",
                             headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                      'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json

        self.assertEqual(resp_json, {"success": {"status": "ok"}}, resp.body)

        users = USERS + [{
            'username': 'testuser4',
            'first_name': 'first',
            'last_name': 'last',
            'created_at': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
            'enabled': True,
            'phone': None,
            'groups': None,
            'department': 'dept',
            'position': 'pos',
            'email': 'email'}]
        self.test_list_users(users=users)

    def test_update_user(self):
        resp = self.app.put(
            '/rest/manage/users/',
            "username=testuser3&password=newpass"
            "&first_name=first&last_name=last&email=new_email"
            "&department=new_dept&position=new_pos&phone=666-666-6666",
            headers={'Cr-Token': 'PREDEFINED_TOKEN',
                     'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json

        self.assertEqual(
            resp_json, {"success": {"status": "ok"}}, resp.body)

        _users = copy(USERS)
        _users[1] = {
            'username': 'testuser3',
            'first_name': 'first',
            'last_name': 'last',
            'created_at': '2014-08-02 00:00:00',
            'enabled': True,
            'phone': '666-666-6666',
            'groups': None,
            'department': 'new_dept',
            'position': 'new_pos',
            'email': 'user3@domain.com'}  # email cannot be changed
        self.test_list_users(users=_users)

    def test_update_user_fail(self):
        resp = self.app.put('/rest/manage/users/',
                            "username=nonexistinguser&email=emailXY"
                            "&first_name=name&last_name=emailXY"
                            "&department=dept&position=p&phone=111-111-1111"
                            "&password=newpass",
                            headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                     'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.body)
        resp_json = resp.json

        self.assertEqual(
            resp_json, {"error": {"msg": "User not found"}}, resp.body)

    def test_update_user_field_fail(self):

        resp = self.app.put('/rest/manage/users/',
                            "username=testuser2&password=newpass",
                            headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                     'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json

        self.assertEqual(
            resp_json, {"error": {"msg": "Field not present: 'first_name'",
                                  "field": "'first_name'"}}, resp.body)

    def test_patch_user(self):
        resp = self.app.patch('/rest/manage/users/',
                              "username=testuser3&password=newpass",
                              headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                       'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json

        self.assertEqual(resp_json, {"success": {"status": "ok"}}, resp.body)

    def test_patch_user_nothing(self):
        resp = self.app.patch('/rest/manage/users/',
                              "username=testuser3",
                              headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                       'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json

        self.assertEqual(
            resp_json, {"success": {"status": "ok"}}, resp.body)

    def test_delete_user(self):
        resp = self.app.delete('/rest/manage/users/testuser3',
                               headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                        'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json

        self.assertEqual(
            resp_json, {"success": {"status": "ok"}}, resp.body)

    def test_delete_user_fail(self):
        resp = self.app.delete('/rest/manage/users/nonexistinguser',
                               headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                        'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json

        self.assertEqual(
            resp_json, {"error": {"msg": "User not found"}}, resp.body)

    # Groups

    def test_create_group(self):
        resp = self.app.post('/rest/manage/groups',
                             "name=new_group",
                             headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                      'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json

        self.assertEqual(resp_json, {"success": {"status": "ok"}}, resp.body)

    def test_modify_group(self):
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

    def test_delete_group(self):
        resp = self.app.delete('/rest/manage/groups/admin',
                               headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                        'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json

        self.assertEqual(
            resp_json, {"success": {"status": "ok"}}, resp.body)

    def test_delete_group_fail(self):
        resp = self.app.delete('/rest/manage/groups/nongroup',
                               headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                        'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json

        self.assertEqual(
            resp_json, {"error": {"msg": "Group not found"}}, resp.body)

    # Roles
    def test_list_roles(self):
        resp = self.app.get('/rest/manage/roles/testuser',
                            headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                     'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json

        self.assertEqual(
            sorted(resp_json['roles']['roles']),
            sorted([
                {"as_user": "root", "group": None, "servers": "*"},
                {"as_user": "guest", "group": None, "servers": "prod.*"},
                {"as_user": "developer", "group": None, "servers": "stg.*"}
            ]))

        self.assertEqual(resp_json['roles']['quota']['allowed'], 5)

    def test_add_roles(self):
        resp = self.app.post('/rest/manage/roles/testuser3',
                             "servers=server3&as_user=ec2-user",
                             headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                      'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json

        self.assertEqual(resp_json, {"success": {"status": "ok"}},
                         resp.body)

    def test_add_roles_wrong_user(self):
        resp = self.app.post('/rest/manage/roles/testuser2',
                             "servers=server3&as_user=ec2-user",
                             headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                      'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json

        self.assertEqual(resp_json, {"error": {"msg": "Cannot create roles"}})

    def test_rm_roles(self):
        self.assertEqual(
            len(self.app.get("/rest/manage/roles/testuser3",
                             headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                      'Cr-User': 'testuser'
                                      }).json['roles']['roles']), 2)
        resp = self.app.delete('/rest/manage/roles/testuser3/developer/dev.*',
                               headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                        'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json

        self.assertEqual(
            len(self.app.get("/rest/manage/roles/testuser3",
                             headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                      'Cr-User': 'testuser'}
                             ).json['roles']['roles']), 1)
        self.assertEqual(resp_json, {"success": {"status": "ok"}},
                         resp.body)

    def test_rm_roles_no_user(self):
        resp = self.app.delete('/rest/manage/roles/testuser2/developer/stg.*',
                               headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                        'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json
        self.assertEqual(resp_json, {"error": {"msg": "Cannot modify roles"}})

    def test_list_orgs_no_perm(self):
        self.assertRaises(webtest.app.AppError,
                          self.app.get, '/rest/manage/orgs/',
                          headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                   'Cr-User': 'testuser'})
