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

    def test_list_logs(self):
        logs = [
            {
                'uuid': '3333333333',
                'source_type': None,
                'created_at': '2014-08-03 00:00:00',
                'tags': None,
                'exit_code': -1,
                'source': None,
                'user': 'testuser',
                'timeout': None,
                'targets': ['*', 'nodeX nodeY']
            }, {
                'uuid': '2222222222',
                'source_type': None,
                'created_at': '2014-08-02 00:00:00',
                'tags': ['tag1', 'tag2'],
                'exit_code': 0,
                'source': None,
                'user': 'testuser',
                'timeout': None,
                'targets': None
            }, {
                'uuid': '1111111111',
                'source_type': None,
                'created_at': '2014-08-01 00:00:00',
                'tags': None,
                'exit_code': -99,
                'source': None,
                'user': 'testuser',
                'timeout': None,
                'targets': None
            }
        ]

        resp = self.app.get('/rest/logs/all', headers={
            'Cr-Token': 'PREDEFINED_TOKEN', 'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json
        self.assertEqual(resp_json['logs'], logs, resp_json)

    def test_get_log(self):
        log = {'created_at': '2014-08-01 00:00:00',
               'exit_code': -99,
               'status': 'Running',
               'steps': [],
               'timeout': None,
               'uuid': '1111111111'
               }

        resp = self.app.get('/rest/logs/get/1111111111', headers={
            'Cr-Token': 'PREDEFINED_TOKEN', 'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json
        self.assertEqual(resp_json['log'], log)

    def test_get_wrong_log(self):

        resp = self.app.get('/rest/logs/get/0000000000', headers={
            'Cr-Token': 'PREDEFINED_TOKEN', 'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json
        self.assertEqual(resp_json['error'], {'msg': 'Log not found'})
