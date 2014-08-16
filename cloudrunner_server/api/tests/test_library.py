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

    def test_list_scripts(self):
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

        resp = self.app.get('/rest/library/scripts', headers={
            'Cr-Token': 'PREDEFINED_TOKEN', 'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        self.assertEqual(resp_json['scripts'], cr_data)

    def test_show_script(self):
        resp = self.app.get('/rest/library/scripts/test/wf1',
                            headers={
                                'Cr-Token': 'PREDEFINED_TOKEN',
                                'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        self.assertEqual(resp_json['script'],
                         {"content": "#! switch [*]\nhostname",
                          "owner": "testuser",
                          "visibility": "public",
                          'created_at': '2014-01-10 00:00:00',
                          "name": "test/wf1"})

    def test_create_script(self):
        resp = self.app.post('/rest/library/scripts',
                             "name=wf1&content=some content",
                             headers={
                                 'Cr-Token': 'PREDEFINED_TOKEN',
                                 'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        self.assertEqual(resp_json, {"status": "ok"},
                         resp.body)
        self.assertRedisInc('library.scripts')
        self.assertRedisPub('library.scripts', 'add')

    def test_create_script_private(self):
        resp = self.app.post('/rest/library/scripts',
                             "name=wf1&content=some content&private=1",
                             headers={
                                 'Cr-Token': 'PREDEFINED_TOKEN',
                                 'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        self.assertEqual(resp_json, {"status": "ok"},
                         resp.body)
        self.assertRedisInc('library.scripts')
        self.assertRedisPub('library.scripts', 'add')

    def test_create_fail_script(self):
        resp = self.app.post('/rest/library/scripts',
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

    def test_update_script(self):
        resp = self.app.put('/rest/library/scripts',
                            "name=test/wf1&content=some modified content",
                            headers={
                                'Cr-Token': 'PREDEFINED_TOKEN',
                                'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        self.assertEqual(resp_json, {"status": "ok"},
                         resp.body)

        self.assertRedisInc('library.scripts')
        self.assertRedisPub('library.scripts', 'update')

    def test_delete_script(self):
        resp = self.app.delete('/rest/library/scripts/test/wf1',
                               headers={
                                   'Cr-Token': 'PREDEFINED_TOKEN',
                                   'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        self.assertEqual(resp_json, {"status": "ok"},
                         resp.body)

        self.assertRedisInc('library.scripts')
        self.assertRedisPub('library.scripts', 'delete')

    def test_delete_fail_script(self):
        resp = self.app.delete('/rest/library/scripts/test/non-existing',
                               headers={
                                   'Cr-Token': 'PREDEFINED_TOKEN',
                                   'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        self.assertEqual(resp_json, {"error": "Script not found!"},
                         resp.body)

        self.assertRedisInc(None)
        self.assertRedisPub(None, None)
