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
        cr_data = {'folders': [
                   {'owner': 'testuser',
                    'id': 3,
                    'full_name':
                    '/folder1/',
                    'name': '/folder1'}
                   ],
                   'scripts': []}

        resp = self.app.get('/rest/library/browse/cloudrunner', headers={
            'Cr-Token': 'PREDEFINED_TOKEN', 'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        self.assertEqual(resp_json['contents'], cr_data, resp_json['contents'])

    def test_show_script(self):
        resp = self.app.get(
            '/rest/library/script/cloudrunner/folder1/folder11/test2',
            headers={
            'Cr-Token': 'PREDEFINED_TOKEN',
            'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        result = {u"content": u"#! switch [*]\ncloudrunner-node details",
                  u"owner": u"testuser",
                  u"mime": u"text/workflow",
                  u'created_at': u'2014-01-20 00:00:00',
                  u"name": u"test2"}
        self.assertEqual(resp_json['script'], result)

    def test_create_script(self):
        resp = self.app.post('/rest/library/script',
                             "name=scr1&content=some content"
                             "&folder=cloudrunner/folder1/",
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
        resp = self.app.post('/rest/library/script',
                             "name=scr1&content=some content"
                             "&folder=private/folder1/",
                             headers={
                                 'Cr-Token': 'PREDEFINED_TOKEN',
                                 'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        self.assertEqual(
            resp_json, {
                "error": {"msg": "Folder private/folder1/ is not accessible"}},
            resp.body)
        self.assertRedisInc(None)
        self.assertRedisPub(None, None)

    def test_update_script(self):
        resp = self.app.put('/rest/library/script',
                            "name=test1&content=some modified content"
                            "&folder=cloudrunner/folder1/",
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
        resp = self.app.delete(
            '/rest/library/script/cloudrunner/folder1/test1',
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
        resp = self.app.delete(
            '/rest/library/script/cloudrunner/folder1/test111',
            headers={
                'Cr-Token': 'PREDEFINED_TOKEN',
                'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        self.assertEqual(
            resp_json, {"error": {"msg": "Script 'test111' not found"}},
            resp.body)

        self.assertRedisInc(None)
        self.assertRedisPub(None, None)

    def test_delete_repo_fail_script(self):
        resp = self.app.delete('/rest/library/script/private/folder1/test1',
                               headers={
                                   'Cr-Token': 'PREDEFINED_TOKEN',
                                   'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        self.assertEqual(
            resp_json, {"error": {"msg": "Script 'test1' not found"}},
            resp.body)

        self.assertRedisInc(None)
        self.assertRedisPub(None, None)
