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
from mock import Mock, patch

from cloudrunner_server.core import message as M
from cloudrunner_server.api.tests import base

ctx_mock = Mock()
sock_mock = Mock()
ctx_mock.socket.return_value = sock_mock


class TestDeployments(base.BaseRESTTestCase):

    def test_list_deployments(self):
        cr_data = {
            'deployments': [
                {'content': '{"steps": [{"content": {"path": "/test/test2@HEAD", '  # noqa
                 '"env": {"a": "env_A"}}, "target": [{"name": "3232", "key_name": '  # noqa
                 '"ttrifonov", "image": "ami-59ecd169", "number": "1", "provider": "aws", '  # noqa
                 '"inst_type": "t2.micro"}]}, {"content": {"path": "/test/test3@HEAD", '  # noqa
                 '"env": {"a": "env_A"}}, "target": ["yoga3"]}, '
                 '{"content": {"path": "/test/test2@HEAD"}, "target": ["yoga3"]}], '  # noqa
                 '"env": {}}',
                 'status': 'Pending', 'created_at': '2015-05-22 00:00:00',
                 'enabled': True, 'name': 'My deployment'},
                 {'content': '{"steps": [{"content": {"path": "/cloudrunner/folder1/test1@HEAD", '  # noqa
                 '"env": {"a": "env_A"}}, "target": [{"name": "3232", "key_name": '  # noqa
                 '"ttrifonov", "image": "ami-59ecd169", "number": "1", "provider": "aws", '  # noqa
                 '"inst_type": "t2.micro"}]}, {"content": {"path": "/cloudrunner/folder1/test1@HEAD", '  # noqa
                 '"env": {"a": "env_A"}}, "target": ["yoga3"]}, '
                 '{"content": {"path": "/cloudrunner/folder1/test1@HEAD"}, "target": ["yoga3"]}], '  # noqa
                 '"env": {}}',
                 'status': 'Running', 'created_at': '2015-05-22 00:00:00',
                 'enabled': True, 'name': 'My running deployment'}]}

        resp = self.app.get('/rest/deployments/deployments', headers={
            'Cr-Token': 'PREDEFINED_TOKEN', 'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        self.assertEqual(resp_json, cr_data)

    @patch('zmq.Context', Mock(return_value=ctx_mock))
    def test_rebuild_deployment(self):
        sock_mock.recv.return_value = M.Queued(
            task_ids=['e7e0b993f1b14bc1be0e6f8c2d57bf16'])._

        resp = self.app.put('/rest/deployments/deployments/My deployment',
            'content=%7B%22steps%22%3A+%5B%7B%22content%22%3A+%7B%22path%22%3A+%22%2Fcloudrunner%2Ffolder1%2Ftest1%40HEAD%22%7D%2C+%22target%22%3A+%5B%22*%22%5D%7D%5D%7D',  # noqa
                              headers={
                                  'Cr-Token': 'PREDEFINED_TOKEN',
                                  'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        resp_json['success']['task_ids']['task_uid'] = '1'
        self.assertEqual(resp_json, {'success': {
            'msg': 'Rebuilt',
            'task_ids': {
                   'task_uid': '1'}}})

    @patch('zmq.Context', Mock(return_value=ctx_mock))
    def test_restart_deployment(self):
        sock_mock.recv.return_value = M.Queued(
            task_ids=['e7e0b993f1b14bc1be0e6f8c2d57bf16'])._

        resp = self.app.post('/rest/deployments/restart/My running deployment',
                             headers={
                                 'Cr-Token': 'PREDEFINED_TOKEN',
                                 'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)
        resp_json['success']['task_ids']['task_uid'] = '1'
        self.assertEqual(resp_json,
                         {'success':
                          {'msg': 'Started', 'task_ids': {'task_uid': '1'}}})

    def test_stop_deployment(self):
        resp = self.app.post('/rest/deployments/stop/My running deployment',
                             headers={
                                 'Cr-Token': 'PREDEFINED_TOKEN',
                                 'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)
        self.assertEqual(resp_json, {'success': {'status': 'ok'}})

    def test_delete_deployment(self):

        resp = self.app.delete('/rest/deployments/deployments/My deployment',
                               headers={
                                   'Cr-Token': 'PREDEFINED_TOKEN',
                                   'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        self.assertEqual(resp_json, {"success": {"status": "ok"}})
