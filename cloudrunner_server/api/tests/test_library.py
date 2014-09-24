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

    def test_list_repos(self):
        cr_data = {'repositories': [
            {'owner': 'testuser',
             'is_link': None,
             'name': 'cloudrunner',
             'private': False},
            {'owner': 'testuser',
             'is_link': None,
             'name': 'empty_repo',
             'private': False}]}

        resp = self.app.get('/rest/library/repo', headers={
            'Cr-Token': 'PREDEFINED_TOKEN', 'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        self.assertEqual(resp_json, cr_data, resp_json)

    def test_create_repo(self):
        resp = self.app.post('/rest/library/repo',
                             "name=newrepo&private=0,is_link=1"
                             "&folder=cloudrunner/folder1/",
                             headers={
                                 'Cr-Token': 'PREDEFINED_TOKEN',
                                 'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        self.assertEqual(resp_json, {'success': {'status': 'ok'}}, resp_json)

    def test_create_repo_fail_name(self):
        resp = self.app.post('/rest/library/repo',
                             "name=empty_repo&private=0,is_link=1"
                             "&folder=cloudrunner/folder1/",
                             headers={
                                 'Cr-Token': 'PREDEFINED_TOKEN',
                                 'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        self.assertEqual(resp_json['error']['reason'], 'duplicate', resp_json)

    def test_delete_repo(self):
        resp = self.app.delete('/rest/library/repo/empty_repo',
                               headers={
                                   'Cr-Token': 'PREDEFINED_TOKEN',
                                   'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        self.assertEqual(resp_json,
                         {'success': {'status': 'ok'}},
                         resp_json)

    def test_delete_repo_fail_non_empty(self):
        resp = self.app.delete('/rest/library/repo/cloudrunner',
                               headers={
                                   'Cr-Token': 'PREDEFINED_TOKEN',
                                   'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        self.assertEqual(resp_json,
                         {'error': 'Cannot remove repo, not empty'},
                         resp_json)

    def test_create_folder(self):
        resp = self.app.post('/rest/library/folder',
                             "name=folder_new"
                             "&folder=cloudrunner/folder1/",
                             headers={
                                 'Cr-Token': 'PREDEFINED_TOKEN',
                                 'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        self.assertEqual(resp_json, {'success': {'status': 'ok'}}, resp_json)

    def test_create_folder_fail_name(self):
        resp = self.app.post('/rest/library/folder',
                             "name=folder11"
                             "&folder=cloudrunner/folder1/",
                             headers={
                                 'Cr-Token': 'PREDEFINED_TOKEN',
                                 'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        self.assertEqual(resp_json['error'],
                         {'msg': 'Duplicate entry into database. '
                          'Check data', 'reason': 'duplicate'})

    def test_delete_folder(self):
        resp = self.app.delete(
            '/rest/library/folder/cloudrunner/folder1/folder11',
            headers={
                'Cr-Token': 'PREDEFINED_TOKEN',
                'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        self.assertEqual(resp_json,
                         {'success': {'status': 'ok'}},
                         resp_json)

    def test_list_scripts(self):
        cr_data = {'folders': [
                   {'owner': 'testuser',
                    'id': 4,
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
            headers={'Cr-Token': 'PREDEFINED_TOKEN', 'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        result = {"script": {
                  "content": "Version 4 Final",
                  "owner": "testuser",
                  "mime": "text/workflow",
                  'created_at': '2014-01-20 00:00:00',
                  "name": "test2",
                  "version": "4"}}
        self.assertEqual(resp_json, result)

        resp = self.app.get(
            '/rest/library/script/cloudrunner/folder1/test1',
            headers={'Cr-Token': 'PREDEFINED_TOKEN', 'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        result = {"script": {
                  "content": "Version 7",
                  "owner": "testuser",
                  "mime": "text/plain",
                  'created_at': '2014-01-10 00:00:00',
                  "name": "test1",
                  'version': '2'}}
        self.assertEqual(resp_json, result)

    def test_create_script(self):
        resp = self.app.post('/rest/library/script',
                             "name=scr1&content=some content"
                             "&folder=cloudrunner/folder1/",
                             headers={
                                 'Cr-Token': 'PREDEFINED_TOKEN',
                                 'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        self.assertEqual(resp_json, {"success": {"status": "ok"}},
                         resp.body)
        self.assertRedisInc('scripts:create')
        self.assertRedisPub('scripts:create', 5)

        resp = self.app.get(
            '/rest/library/script/cloudrunner/folder1/scr1',
            headers={'Cr-Token': 'PREDEFINED_TOKEN', 'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        resp_json['script'].pop('created_at')
        result = {"script": {
                  "content": "some content",
                  "owner": "testuser",
                  "mime": "text/plain",
                  "name": "scr1",
                  'version': '1'}}
        self.assertEqual(resp_json, result)

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

        self.assertEqual(resp_json, {"success": {"status": "ok"}},
                         resp.body)

        self.assertRedisInc('scripts:modify')
        self.assertRedisPub('scripts:modify', 1)

    def test_delete_script(self):
        resp = self.app.delete(
            '/rest/library/script/cloudrunner/folder1/test1',
            headers={
                'Cr-Token': 'PREDEFINED_TOKEN',
                'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        self.assertEqual(resp_json, {"success": {"status": "ok"}},
                         resp.body)

        self.assertRedisInc('scripts:delete')
        self.assertRedisPub('scripts:delete', 1)

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
