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

import json

from cloudrunner_server.api.tests import base


class TestLibrary(base.BaseRESTTestCase):

    def test_list_workflows(self):
        cr_data = {
            'cloudrunner': [
                {
                    'owner': 'testuser',
                    'created_at': '2014-01-10 00:00:00',
                    'name': 'test/wf1',
                    'visibility': 'public'
                },
                {
                    'owner': 'testuser',
                    'created_at': '2014-01-20 00:00:00',
                    'name': 'test/wf2',
                    'visibility': 'private'
                },
                {
                    'owner': 'testuser',
                    'created_at': '2014-01-30 00:00:00',
                    'name': 'test/wf3',
                    'visibility': 'public'
                }
            ]
        }

        resp = self.app.get('/rest/library/workflows', headers={
            'Cr-Token': 'PREDEFINED_TOKEN', 'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        self.assertEqual(resp_json['workflows'], cr_data)

    def test_show_workflow(self):
        resp = self.app.get('/rest/library/workflows/test/wf1',
                            headers={
                                'Cr-Token': 'PREDEFINED_TOKEN',
                                'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        self.assertEqual(resp_json['workflow'],
                         {"content": "#! switch [*]\nhostname",
                          "owner": "testuser",
                          "visibility": "public",
                          'created_at': '2014-01-10 00:00:00',
                          "name": "test/wf1"})

    def test_create_workflow(self):
        resp = self.app.post('/rest/library/workflows',
                             "name=wf1&content=some content",
                             headers={
                                 'Cr-Token': 'PREDEFINED_TOKEN',
                                 'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        self.assertEqual(resp_json, {"status": "ok"},
                         resp.body)
        self.assertRedisInc('MyOrg:library.workflows')
        self.assertRedisPub('MyOrg:library.workflows', 'add')

    def test_create_workflow_private(self):
        resp = self.app.post('/rest/library/workflows',
                             "name=wf1&content=some content&private=1",
                             headers={
                                 'Cr-Token': 'PREDEFINED_TOKEN',
                                 'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        self.assertEqual(resp_json, {"status": "ok"},
                         resp.body)
        self.assertRedisInc('MyOrg:library.workflows')
        self.assertRedisPub('MyOrg:library.workflows', 'add')

    def test_create_fail_workflow(self):
        resp = self.app.post('/rest/library/workflows',
                             "name=wf1&",
                             headers={
                                 'Cr-Token': 'PREDEFINED_TOKEN',
                                 'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        self.assertEqual(resp_json, {"error": "Value not present: 'content'"},
                         resp.body)
        self.assertRedisInc(None)
        self.assertRedisPub(None, None)

    def test_update_workflow(self):
        resp = self.app.put('/rest/library/workflows',
                            "name=test/wf1&content=some modified content",
                            headers={
                                'Cr-Token': 'PREDEFINED_TOKEN',
                                'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        self.assertEqual(resp_json, {"status": "ok"},
                         resp.body)

        self.assertRedisInc('MyOrg:library.workflows')
        self.assertRedisPub('MyOrg:library.workflows', 'update')

    def test_delete_workflow(self):
        resp = self.app.delete('/rest/library/workflows/test/wf1',
                               headers={
                                   'Cr-Token': 'PREDEFINED_TOKEN',
                                   'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        self.assertEqual(resp_json, {"status": "ok"},
                         resp.body)

        self.assertRedisInc('MyOrg:library.workflows')
        self.assertRedisPub('MyOrg:library.workflows', 'delete')

    def test_delete_fail_workflow(self):
        resp = self.app.delete('/rest/library/workflows/test/non-existing',
                               headers={
                                   'Cr-Token': 'PREDEFINED_TOKEN',
                                   'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        self.assertEqual(resp_json, {"error": "Workflow not found!"},
                         resp.body)

        self.assertRedisInc(None)
        self.assertRedisPub(None, None)

    def test_list_inlines(self):
        cr_data = [
            {
                "owner": "testuser",
                "visibility": "public",
                "name": "tools/ifconfig"},
            {
                "owner": "testuser",
                "visibility": "private",
                "name": "tools/nginx_status"
            }
        ]

        resp = self.app.get('/rest/library/inlines', headers={
            'Cr-Token': 'PREDEFINED_TOKEN', 'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        self.assertEqual(resp_json['inlines'], cr_data)

    def test_show_inline(self):
        resp = self.app.get('/rest/library/inlines/tools/ifconfig',
                            headers={
                                'Cr-Token': 'PREDEFINED_TOKEN',
                                'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        self.assertEqual(resp_json['inline'],
                         {"content": "/sbin/ifconfig",
                          "owner": "testuser",
                          "visibility": "public",
                          "name": "tools/ifconfig"}, resp.body)

    def test_create_inline(self):
        resp = self.app.post('/rest/library/inlines',
                             "name=wf1&content=some content",
                             headers={
                                 'Cr-Token': 'PREDEFINED_TOKEN',
                                 'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        self.assertEqual(resp_json, {"status": "ok"},
                         resp.body)
        self.assertRedisInc('MyOrg:library.inlines')
        self.assertRedisPub('MyOrg:library.inlines', 'add')

    def test_create_inline_private(self):
        resp = self.app.post('/rest/library/inlines',
                             "name=wf1&content=some content&private=1",
                             headers={
                                 'Cr-Token': 'PREDEFINED_TOKEN',
                                 'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        self.assertEqual(resp_json, {"status": "ok"},
                         resp.body)
        self.assertRedisInc('MyOrg:library.inlines')
        self.assertRedisPub('MyOrg:library.inlines', 'add')

    def test_create_inline_fail(self):
        resp = self.app.post('/rest/library/inlines',
                             "name=wf1&",
                             headers={
                                 'Cr-Token': 'PREDEFINED_TOKEN',
                                 'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        self.assertEqual(resp_json, {"error": "Value not present: 'content'"},
                         resp.body)
        self.assertRedisInc(None)
        self.assertRedisPub(None, None)

    def test_update_inline(self):
        resp = self.app.put('/rest/library/inlines',
                            "name=tools/nginx_status&content="
                            "some modified content",
                            headers={
                                'Cr-Token': 'PREDEFINED_TOKEN',
                                'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        self.assertEqual(resp_json, {"status": "ok"},
                         resp.body)
        self.assertRedisInc('MyOrg:library.inlines')
        self.assertRedisPub('MyOrg:library.inlines', 'update')

    def test_delete_inline(self):
        resp = self.app.delete('/rest/library/inlines/tools/nginx_status',
                               headers={
                                   'Cr-Token': 'PREDEFINED_TOKEN',
                                   'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        self.assertRedisInc('MyOrg:library.inlines')
        self.assertRedisPub('MyOrg:library.inlines', 'delete')

        self.assertEqual(resp_json, {"status": "ok"},
                         resp.body)

    def test_delete_inline_fail(self):
        resp = self.app.delete('/rest/library/inlines/test/non-existing',
                               headers={
                                   'Cr-Token': 'PREDEFINED_TOKEN',
                                   'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        self.assertRedisInc(None)
        self.assertRedisPub(None, None)

        self.assertEqual(resp_json, {"error": "Inline not found!"},
                         resp.body)
