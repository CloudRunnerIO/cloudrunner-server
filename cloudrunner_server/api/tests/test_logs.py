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


class TestLogs(base.BaseRESTTestCase):

    def setUp(self):
        super(TestLogs, self).setUp()

    def test_list_logs(self):
        tasks = {
            'etag': 1000,
            'groups': [
                {
                    'status': 2,
                    'lang': 'python',
                    'uuid': '1111111111', 'group': None,
                    'target': 'nodes', 'step': None,
                    'source': '',
                    'created_at': '2014-01-01 00:00:00',
                    'exit_code': 1,
                    'parent_id': None,
                    'job': None,
                    'taskgroup_id': None,
                    'owner': 'testuser',
                    'total_steps': None,
                    'revision': '4',
                    'name': 'cloudrunner/folder1/folder11/test2'
                }]}
        resp = self.app.get('/rest/logs/all', headers={
            'Cr-Token': 'PREDEFINED_TOKEN', 'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json
        self.assertEqual(resp_json['tasks'], tasks)

    def test_get_log(self):
        log = {
            'task':
              {
                  'status': 'Finished',
                  'lang': 'python',
                  'uuid': '1111111111',
                  'script': "script",
                  'created_at': '2014-01-01 00:00:00',
                  'exit_code': 1,
                  'timeout': 60,
                  'env': {"key": "value"},
                  'target': 'nodes'
              }
        }
        resp = self.app.get('/rest/logs/get?log_uuid=1111111111', headers={
            'Cr-Token': 'PREDEFINED_TOKEN', 'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json
        self.assertEqual(resp_json, log, resp_json)

    def test_get_wrong_log(self):

        resp = self.app.get('/rest/logs/get/0000000000', headers={
            'Cr-Token': 'PREDEFINED_TOKEN', 'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json
        self.assertEqual(resp_json['error'], {'msg': 'Log not found'})
