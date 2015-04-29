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
            'marker': None,
            'etag': 0,
            'pages': 1,
            'groups':
            [{
                'status': 2,
                'group': 1,
                'uuid': '1111111111',
                'script_name': 'cloudrunner/folder1/test1',
                'exec_end': None,
                'created_at': '2014-01-01 00:00:00',
                'exit_code': 1,
                'batch': {},
                'parent_id': None,
                'exec_start': None,
                'owner': 'testuser',
                'nodes': [{'exit': 0, 'name': 'node1'},
                          {'exit': 1, 'name': 'node3'}],
                'id': 1,
                'revision': '2'
            }]
        }
        resp = self.app.get('/rest/logs/all', headers={
            'Cr-Token': 'PREDEFINED_TOKEN', 'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json
        self.maxDiff = None
        self.assertEqual(resp_json['tasks'], tasks)

    def test_get_log(self):
        log = {
            'group': {'workflows':
                      [
                          {'status': 'Finished',
                           'script_name': 'cloudrunner/folder1/test1',
                           'runs': [
                               {'lang': 'python',
                                'uuid': '222222222',
                                'full_script': 'Version 7',
                                'exit_code': 2,
                                'env_in': {'key': 'value'},
                                'exec_start': 100000000,
                                'step_index': 1,
                                'timeout': 90,
                                'nodes': [{'exit': 0, 'name': 'node1'},
                                          {'exit': 1, 'name': 'node3'}],
                                   'env_out': {},
                                'exec_end': 1000000010,
                                'target': 'node1 node3'}],
                              'uuid': '1111111111',
                              'created_at': '2014-01-01 00:00:00',
                              'exit_code': 1, 'timeout': 90}
                      ]}
        }

        resp = self.app.get('/rest/logs/get?log_uuid=1111111111', headers={
            'Cr-Token': 'PREDEFINED_TOKEN', 'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json
        self.assertEqual(resp_json, log)

    def test_get_wrong_log(self):

        resp = self.app.get('/rest/logs/get/0000000000', headers={
            'Cr-Token': 'PREDEFINED_TOKEN', 'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json
        self.assertEqual(resp_json, {'task': {}})
