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
        nodes = [{
            u'name': u'node1',
            u'tags': [],
            u'enabled': True,
            u'joined_at': u'2014-01-01 00:00:00',
            u'meta': {u'ID': u'NODE1'},
            u'approved_at': u'2014-01-01 00:00:00',
            u'approved': True,
            u'auto_cleanup': None
        }, {
            u'name': u'node3',
            u'tags': [],
            u'enabled': True,
            u'joined_at': u'2014-09-01 00:00:00',
            u'meta': {u'ID': u'NODE3'},
            u'approved_at': u'2014-11-01 00:00:00',
            u'approved': True,
            u'auto_cleanup': None
        }, {
            u'name': u'node4',
            u'tags': [],
            u'enabled': True,
            u'joined_at': u'2014-09-01 00:00:00',
            u'meta': {u'ID': u'NODE4'},
            u'approved_at': None,
            u'approved': False,
            u'auto_cleanup': None}
        ]

        resp = self.app.get('/rest/manage/nodes', headers={
            'Cr-Token': 'PREDEFINED_TOKEN', 'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)['nodes']
        self.assertEqual(resp_json, nodes, resp_json)

    @patch('cloudrunner_server.api.controllers.nodes.CertController')
    def test_sign_nodes(self, cert):
        cert().sign_node = Mock(return_value=('', 'file'))

        resp = self.app.put('/rest/manage/nodes',
                            'node=node4',
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

    @patch('cloudrunner_server.api.controllers.nodes.CertController')
    def test_revoke_nodes(self, cert):
        cert().revoke = Mock(
            return_value=([1, ''],
                          [2, 'Certificate for node [node1] revoked']))

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

    def test_list_groups(self):
        nodegroups = {'name': 'one_two',
                      'members': ['node1', 'node2']}

        resp = self.app.get('/rest/manage/nodegroups',
                            headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                     'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)
        self.assertEqual(len(resp_json['groups']), 1)
        self.assertEqual(sorted(resp_json['groups'][0]['members']),
                         sorted(nodegroups['members']))
        self.assertEqual(sorted(resp_json['groups'][0]['name']),
                         sorted(nodegroups['name']))

    def test_create_group(self):
        resp = self.app.post('/rest/manage/nodegroups',
                             dict(name="new group"),
                             headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                      'Cr-User': 'testuser'},
                             )
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)
        self.assertEqual(resp_json, {'success': {'status': 'ok'}}, resp_json)

    def test_add_node_to_group(self):
        resp = self.app.patch('/rest/manage/nodegroups/one_two',
                              {'nodes': ["node4", "node2"]},
                              headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                       'Cr-User': 'testuser'},
                              )
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)
        self.assertEqual(resp_json, {'success': {'status': 'ok'}}, resp_json)

        nodegroups = {u'groups': [
            {u'name': u'one_two',
             u'members': [u'node2', u'node4']}]}

        resp = self.app.get('/rest/manage/nodegroups',
                            headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                     'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)
        self.assertEqual(resp_json, nodegroups)

    def test_remove_node_to_group(self):
        resp = self.app.patch('/rest/manage/nodegroups/one_two',
                              {'nodes': "node2"},
                              headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                       'Cr-User': 'testuser'},
                              )
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)
        self.assertEqual(resp_json, {'success': {'status': 'ok'}}, resp_json)

        nodegroups = {u'groups': [
            {u'name': u'one_two',
             u'members': [u'node2']}]}

        resp = self.app.get('/rest/manage/nodegroups',
                            headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                     'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)
        self.assertEqual(resp_json, nodegroups)

    def test_remove_group(self):
        resp = self.app.delete('/rest/manage/nodegroups/one_two',
                               headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                        'Cr-User': 'testuser'},
                               )
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)
        self.assertEqual(resp_json, {'success': {'status': 'ok'}}, resp_json)

        nodegroups = {u'groups': []}

        resp = self.app.get('/rest/manage/nodegroups',
                            headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                     'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)
        self.assertEqual(resp_json, nodegroups)
