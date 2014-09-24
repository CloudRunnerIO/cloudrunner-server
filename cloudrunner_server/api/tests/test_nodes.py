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
from cloudrunner_server.api.tests import base


class TestNodes(base.BaseRESTTestCase):

    def test_list_nodes(self):
        nodes = {'nodes': [
            {'joined_at': '2014-01-01 00:00:00',
                'meta': {'ID': 'NODE1'},
                'approved_at': '2014-01-01 00:00:00',
                'name':
                'node1',
                'approved': True
             },
            {
                'joined_at': '2014-04-01 00:00:00',
                'meta': {'ID': 'NODE2'},
                'approved_at': None,
                'name': 'node2',
                'approved': False},
            {
                'joined_at': '2014-09-01 00:00:00',
                'meta': {'ID': 'NODE3'},
                'approved_at': '2014-11-01 00:00:00',
                'name': 'node3',
                'approved': True}]}

        resp = self.app.get('/rest/manage/nodes', headers={
            'Cr-Token': 'PREDEFINED_TOKEN', 'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)
        self.assertEqual(resp_json, nodes, resp_json)

    @patch('cloudrunner_server.api.v0_9.controllers.nodes.CertController')
    def test_sign_nodes(self, cert):
        cert().sign_node = Mock(return_value=('', 'file'))

        resp = self.app.put('/rest/manage/nodes',
                            'node=node2',
                            headers={
                                'Cr-Token': 'PREDEFINED_TOKEN',
                                'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)
        self.assertEqual(resp_json, {'success': {'status': 'ok'}}, resp_json)

    def test_sign_nodes_fail(self):
        resp = self.app.put('/rest/manage/nodes',
                            'node=node1',
                            headers={
                                'Cr-Token': 'PREDEFINED_TOKEN',
                                'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)
        self.assertEqual(resp_json, {'error': {'msg': 'Node not found'}},
                         resp_json)

    @patch('cloudrunner_server.api.v0_9.controllers.nodes.CertController')
    def test_revoke_nodes(self, cert):
        cert().revoke = Mock(
            return_value=('', 'Certificate for node [node1] revoked'))

        resp = self.app.delete('/rest/manage/nodes/node1',
                               headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                        'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)
        self.assertEqual(resp_json, {'success': {'status': 'ok'}}, resp_json)

    def test_revoke_nodes_fail(self):
        resp = self.app.delete('/rest/manage/nodes/node2',
                               headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                        'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)
        self.assertEqual(resp_json, {'error': {'msg': 'Node not found'}},
                         resp_json)
