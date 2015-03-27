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
from datetime import datetime
from mock import patch, Mock

from cloudrunner_server.api.tests import base
from cloudrunner_server.plugins.repository.base import NotModified


class TestLibrary(base.BaseRESTTestCase):

    def test_list_repos(self):
        cr_data = {'repositories': [
            {
                'name': 'cloudrunner',
                'editable': True,
                'enabled': True,
                'private': False,
                'owner': 'testuser',
                'type': 'cloudrunner'
            }, {
                'name': 'empty_repo',
                'editable': True,
                'enabled': True,
                'private': False,
                'owner': 'testuser',
                'type': 'cloudrunner'
            }, {
                'name': 'ext_repo',
                'editable': True,
                'enabled': True,
                'private': True,
                'owner': 'testuser',
                'type': 'github'}
        ],
            'quota': {'total': 5, 'external': False, 'user': 5}}

        resp = self.app.get('/rest/library/repo', headers={
            'Cr-Token': 'PREDEFINED_TOKEN', 'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        self.assertEqual(resp_json, cr_data)

    def test_create_repo(self):
        resp = self.app.post('/rest/library/repo',
                             "name=newrepo&private=0&type=cloudrunner"
                             "&folder=cloudrunner/folder1/",
                             headers={
                                 'Cr-Token': 'PREDEFINED_TOKEN',
                                 'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        self.assertEqual(resp_json, {'success': {'status': 'ok'}}, resp_json)

    def test_create_ext_repo(self):
        resp = self.app.post('/rest/library/repo',
                             "name=newrepo&private=0&type=github"
                             "&folder=cloudrunner/folder1/&user=gituser"
                             "&pass=gitpass&args=gitargs",
                             headers={
                                 'Cr-Token': 'PREDEFINED_TOKEN',
                                 'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        self.assertEqual(resp_json, {'success': {'status': 'ok'}}, resp_json)

    def test_create_repo_fail_name(self):
        resp = self.app.post('/rest/library/repo',
                             "name=empty_repo&private=0&type=cloudrunner"
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
                         {'error': {'msg': 'Cannot remove repo, not empty'}})

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

    def test_browse_repo(self):
        cr_data = {'folders': [{
            'name': '/folder1',
            'created_at': '2014-01-10 00:00:00',
            'editable': True,
            'etag': None,
            'full_name': '/folder1/',
            'owner': 'testuser',
            'id': 5}],
            'owner': 'testuser', 'editable': True, 'scripts': []
        }

        resp = self.app.get('/rest/library/browse/cloudrunner/', headers={
            'Cr-Token': 'PREDEFINED_TOKEN', 'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)
        self.assertEqual(resp_json['contents'], cr_data)

    def test_browse_repo2(self):
        self.set_user(2)
        cr_data = {
            "contents": {
                "folders": [
                    {
                        "name": "/folder2",
                        "created_at": "2014-02-10 00:00:00",
                        "editable": True,
                        "etag": None,
                        "full_name": "/folder2/",
                        "owner": "testuser2",
                        "id": 6}
                ],
                "owner": "testuser2",
                "editable": True,
                "scripts": []}
        }

        resp = self.app.get('/rest/library/browse/private/', headers={
            'Cr-Token': 'PREDEFINED_TOKEN2', 'Cr-User': 'testuser2'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)
        self.assertEqual(resp_json['contents'], cr_data['contents'])

        cr_data = {
            "contents": {
                "folders": [
                    {
                        "name": "/folder11",
                        "created_at": "2014-01-12 00:00:00",
                        "editable": True,
                        "etag": None,
                        "full_name": "/folder2/folder11/",
                        "owner": "testuser2",
                        "id": 8}
                ],
                "owner": "testuser2",
                "editable": True,
                "scripts": []}
        }
        resp = self.app.get('/rest/library/browse/private/folder2/', headers={
            'Cr-Token': 'PREDEFINED_TOKEN2', 'Cr-User': 'testuser2'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)
        self.assertEqual(resp_json['contents'], cr_data['contents'])

        cr_data = {
            'contents': {
                'folders': [],
                'owner': 'testuser2',
                'editable': True,
                'scripts': [
                    {
                        'name': 'test2',
                        'created_at': '2014-01-30 00:00:00',
                        'editable': True,
                        'etag': None,
                        'version': '1',
                        'allow_sudo': None,
                        'owner': 'testuser2',
                        'id': 4,
                        'mime_type': 'text/workflow'
                    }
                ]
            }}

        resp = self.app.get('/rest/library/browse/private/folder2/folder11',
                            headers={
                                'Cr-Token': 'PREDEFINED_TOKEN2',
                                'Cr-User': 'testuser2'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)
        self.assertEqual(resp_json['contents'], cr_data['contents'])

    @patch('cloudrunner_server.plugins.repository.base.PluginRepoBase')
    def test_browse_ext_repo(self, repobase):
        github = Mock(type='github')
        repobase.__subclasses__ = Mock(return_value=[github])
        contents = {'folders': [{'name': 'ext_folder'}],
                    'scripts': [{'name': 'ext_script'}]}
        last = datetime(2015, 01, 01)
        github().browse.side_effect = [(contents, last, last), NotModified()]

        github().contents = Mock(return_value=("ext script content",
                                               last, 'gitrev123', last))

        cr_data = {'folders': [{
            'name': 'ext_folder',
            'created_at': None,
            'editable': False,
            'etag': None,
            'full_name': '/ext_folder/',
            'owner': 'github',
            'id': 9}],
            'owner': 'testuser', 'editable': False,
            'scripts': [{'allow_sudo': None,
                         'created_at': u'2015-01-01 00:00:00',
                         'editable': False,
                         'etag': u'2015-01-01 00:00:00',
                         'id': 5,
                         'mime_type': u'text/plain',
                         'name': u'ext_script',
                         'owner': u'github',
                         'version': u'gitrev123'}]
        }

        resp = self.app.get('/rest/library/browse/ext_repo/', headers={
            'Cr-Token': 'PREDEFINED_TOKEN', 'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)
        self.assertEqual(resp_json['contents'], cr_data)

        resp = self.app.get('/rest/library/browse/ext_repo/', headers={
            'Cr-Token': 'PREDEFINED_TOKEN', 'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)
        self.assertEqual(resp_json['contents'], cr_data)

    def test_show_script(self):
        resp = self.app.get(
            '/rest/library/script/cloudrunner/folder1/folder11/test2',
            headers={'Cr-Token': 'PREDEFINED_TOKEN', 'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)
        result = {'script': {
            'name': 'test2',
            'created_at': '2014-01-20 00:00:00',
            'content': 'Version 4 Final',
            'version': '4',
            'mime': 'text/workflow',
            "editable": True,
            'allow_sudo': None,
            'owner': 'testuser',
            'revisions': [
                {'created_at': '2014-01-01 10:00:00', 'version': '4'},
                {'created_at': '2014-01-01 08:00:00', 'version': '3'},
                {'created_at': '2014-01-01 07:00:00', 'version': '2'},
                {'created_at': '2014-01-01 06:00:00', 'version': '1'}]}
        }
        self.assertEqual(resp_json['script'], result['script'])

        resp = self.app.get(
            '/rest/library/script/cloudrunner/folder1/test1',
            headers={'Cr-Token': 'PREDEFINED_TOKEN', 'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        result = {'script': {
            'name': 'test1',
            'created_at': '2014-01-10 00:00:00',
            'content': 'Version 7',
            'version': '2',
            'mime': 'text/plain',
            "editable": True,
            'allow_sudo': None,
            'owner': 'testuser',
            'revisions': [
                {'created_at': '2014-01-01 12:00:00', 'version': '2'},
                {'created_at': '2014-01-01 11:00:00', 'version': '1'}]}
        }

        self.assertEqual(resp_json['script'], result['script'])

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

        resp = self.app.get(
            '/rest/library/script/cloudrunner/folder1/scr1',
            headers={'Cr-Token': 'PREDEFINED_TOKEN', 'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        resp_json['script'].pop('created_at')
        for rev in resp_json['script']['revisions']:
            rev.pop('created_at')
        result = {"script": {
            "allow_sudo": None,
            "content": "some content",
            "owner": "testuser",
            "mime": "text/plain",
            "name": "scr1",
            "editable": True,
            'version': '1',
            'revisions': [{'version': '1'}]
        }}
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
                "error": {"msg": "Folder private/folder1/ is not editable"}},
            resp.body)

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

        resp = self.app.get(
            '/rest/library/script/cloudrunner/folder1/test1',
            headers={'Cr-Token': 'PREDEFINED_TOKEN', 'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)
        result = {'script': {
            'name': 'test1',
            'created_at': '2014-01-10 00:00:00',
            'content': 'some modified content',
            'version': '3',
            'mime': 'text/plain',
            'allow_sudo': None,
            "editable": True,
            'owner': 'testuser',
            'revisions': [
                {'version': '3'},
                {'version': '2'},
                {'version': '1'}]}
        }
        for rev in resp_json['script']['revisions']:
            rev.pop('created_at')
        self.assertEqual(resp_json['script'], result['script'])

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

    def test_show_workflow(self):
        resp = self.app.get(
            '/rest/workflows/workflow/cloudrunner/folder1/folder11/test2',
            headers={'Cr-Token': 'PREDEFINED_TOKEN', 'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)
        result = {"workflow":
                  {
                      'editable': True,
                      'rev': '4',
                      'sections': [],
                      'revisions': [
                          {
                              'created_at': '2014-01-01 10:00:00',
                              'version': '4'},
                          {
                              'created_at': '2014-01-01 08:00:00',
                              'version': '3'},
                          {
                              'created_at': '2014-01-01 07:00:00',
                              'version': '2'},
                          {
                              'created_at': '2014-01-01 06:00:00',
                              'version': '1'}
                      ]
                  }}

        self.assertEqual(
            resp_json['workflow'], result['workflow'])

    def test_show_workflow2(self):
        self.set_user(2)
        resp = self.app.get(
            '/rest/workflows/workflow/private/folder2/folder11/test2',
            headers={'Cr-Token': 'PREDEFINED_TOKEN2', 'Cr-User': 'testuser2'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        result = {"workflow": {
            "sections": [
                {
                    "lang": "bash",
                    "include_before": [],
                    "env": {},
                    "content": "echo 'Done'",
                    "timeout": None,
                    "include_after": [],
                    "targets": ["*"],
                    "attachments": []
                }
            ],
            "rev": "1",
            "editable": True,
            "revisions": [
                {
                    "created_at": "2014-01-01 10:00:00",
                    "version": "1"
                }
            ]
        }}

        self.assertEqual(resp_json['workflow'], result['workflow'])
