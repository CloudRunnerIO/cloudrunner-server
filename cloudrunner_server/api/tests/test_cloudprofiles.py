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


class TestCloudProfiles(base.BaseRESTTestCase):

    def test_list_profiles(self):
        cr_data = {
            'quota': {'allowed': 12},
            'profiles': [
                {
                    'username': 'AWS_KEY',
                    'name': 'ProfAWS',
                    'created_at': '2015-05-21 00:00:00',
                    'enabled': True,
                    'shares': [],
                    'clear_nodes': True,
                    'type': 'aws'},
                {
                    'username': 'RAX_user',
                    'name': 'ProfRAX',
                    'created_at': '2015-05-22 00:00:00',
                    'enabled': True,
                    'shares': [{'created_at': '2015-05-23 00:00:00',
                                'name': 'rax-share', 'node_quota': 2}],
                    'clear_nodes': True,
                    'type': 'rackspace'}
            ]}

        resp = self.app.get('/rest/clouds/profiles', headers={
            'Cr-Token': 'PREDEFINED_TOKEN', 'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)
        self.maxDiff = None

        self.assertEqual(resp_json, cr_data)

    def test_create_profile(self):
        cr_data = {
            'quota': {'allowed': 12},
            'profiles': [
                {
                    'username': 'AWS_KEY',
                    'name': 'ProfAWS',
                    'created_at': '2015-05-21 00:00:00',
                    'enabled': True,
                    'shares': [],
                    'clear_nodes': True,
                    'type': 'aws'},
                {
                    'username': 'RAX_user',
                    'name': 'ProfRAX',
                    'created_at': '2015-05-22 00:00:00',
                    'enabled': True,
                    'shares': [{'created_at': '2015-05-23 00:00:00',
                                'name': 'rax-share', 'node_quota': 2}],
                    'clear_nodes': True,
                    'type': 'rackspace'},
                {
                    'username': 'do_prof',
                    'name': 'digitalocean',
                    'enabled': True,
                    'shares': [],
                    'clear_nodes': False,
                    'type': 'digitalocean'}
            ]}

        resp = self.app.post('/rest/clouds/profiles',
            'username=do_prof&password=very_secret&arguments=arghh&name=digitalocean&type=digitalocean&shared=false',  # noqa
            headers={
            'Cr-Token': 'PREDEFINED_TOKEN', 'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        self.assertEqual(resp_json, {"success": {"status": "ok"}})

        resp = self.app.get('/rest/clouds/profiles',
                            headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                     'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)
        resp_json['profiles'][2].pop('created_at')
        self.assertEqual(resp_json, cr_data, resp_json)

    def test_modify_profile(self):
        cr_data = {'profile': {
            'username': 'rax_new',
            'name': 'ProfRAX',
            'created_at': '2015-05-22 00:00:00',
            'enabled': True,
            'shares': [{'created_at': '2015-05-23 00:00:00', 'nodes': [],
                        'name': 'rax-share', 'node_quota': 2}],
            'clear_nodes': True,
            'type': 'rackspace'}}

        resp = self.app.put('/rest/clouds/profiles/ProfRAX',
                            'username=rax_new&password=rax_new_secret&arguments=rax_args',  # noqa
                            headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                     'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        self.assertEqual(resp_json, {"success": {"status": "ok"}})

        resp = self.app.get('/rest/clouds/profiles/ProfRAX',
                            headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                     'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)
        self.assertEqual(resp_json, cr_data, resp_json)

    def test_list_share(self):
        cr_data = {'shares': [
            {
                'created_at': '2015-05-23 00:00:00',
                'node_quota': 2,
                'nodes': [],
                'name': 'rax-share'}
        ]}

        resp = self.app.get('/rest/clouds/shares/ProfRAX', headers={
            'Cr-Token': 'PREDEFINED_TOKEN', 'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        self.assertEqual(resp_json, cr_data, resp_json)

    def test_create_share(self):
        cr_data = {'shares': [
            {
                'created_at': '2015-05-23 00:00:00',
                'node_quota': 2,
                'nodes': [],
                'name': 'rax-share'},
            {
                'node_quota': 0, 'nodes': [],
                'name': 'share_user'}]}

        resp = self.app.post('/rest/clouds/shares/ProfRAX',
                             "name=share_user",
                             headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                      'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        self.assertEqual(resp_json, {"success": {"status": "ok"}})

        resp = self.app.get('/rest/clouds/shares/ProfRAX', headers={
            'Cr-Token': 'PREDEFINED_TOKEN', 'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)
        resp_json['shares'][1].pop('created_at')
        self.assertEqual(resp_json, cr_data)

    def test_delete_share(self):
        cr_data = {'shares': []}

        resp = self.app.delete('/rest/clouds/shares/ProfRAX/rax-share',
                               headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                        'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        self.assertEqual(resp_json, {"success": {"status": "ok"}})

        resp = self.app.get('/rest/clouds/shares/ProfRAX', headers={
            'Cr-Token': 'PREDEFINED_TOKEN', 'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)
        self.assertEqual(resp_json, cr_data)

    def test_delete_profile(self):

        resp = self.app.delete('/rest/clouds/profiles/ProfRAX',
                               headers={
                                   'Cr-Token': 'PREDEFINED_TOKEN',
                                   'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        self.assertEqual(resp_json, {"success": {"status": "ok"}})
