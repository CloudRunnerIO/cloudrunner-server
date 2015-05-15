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
from dateutil import parser
from datetime import datetime, timedelta
from mock import MagicMock
import webtest

from cloudrunner_server.api.tests import base
from cloudrunner_server.api.util import TOKEN_CHARS


class TestAuthentication(base.BaseRESTTestCase):

    def test_login(self):
        now = datetime.now()
        resp = self.app.post('/rest/auth/login',
                             {'username': 'testuser',
                              'password': 'testpassword'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)['login']
        resp_json['expire'] = parser.parse(resp_json['expire'])
        resp_json['expire'] = resp_json['expire'].replace(microsecond=0)

        exact_exp = now + timedelta(minutes=1440)
        self.assertEqual(resp_json['user'], 'testuser')
        self.assertEqual(abs((exact_exp - resp_json['expire']).seconds), 0)
        self.assertTrue(set(resp_json['token']).issubset(set(TOKEN_CHARS)))

        user, args, exp = self.aero.add_token.call_args_list[0][0]
        args.pop('token')
        self.assertEquals(user, 'testuser')
        self.assertEquals(exp, 1440)
        self.maxDiff = None
        self.assertEquals(args,
                          {'email_hash': '3bc81bc52e7f209c3455af320abeee00',
                              'uid': 1,
                              'tier': {
                                  'users': 5, 'max_timeout': 60,
                                  'description': u'Free Tier',
                                  'roles': 4, 'title': u'Free', 'cron_jobs': 4,
                                  'api_keys': 5,
                                  'max_concurrent_tasks': 2, 'total_repos': 5,
                                  'groups': 5,
                                  'external_repos': True, 'nodes': 6,
                                  'log_retention_days': 7,
                                  'deployments': 10, 'cloud_profiles': 12,
                                  'name': u'Free'},
                              'org': u'MyOrg', 'email': u'user1@domain.com',
                              'permissions': [u'is_admin']
                           }
                          )

    def test_fake_login(self):
        resp = self.app.post('/rest/auth/login',
                             {'username': 'testuser',
                              'password': 'wrong_password'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        self.assertEqual(resp_json, {u'error': {u'msg': u'Cannot login'}})

    def test_unauthorized_call(self):
        self.aero_reader.get_user_token = MagicMock(return_value=None)
        self.assertRaises(webtest.app.AppError,
                          self.app.get, '/rest/library/browse/repo1',
                          headers={'Cr-Token': 'NON_EXISTING_TOKEN',
                                   'Cr-User': 'testuser'})

    def test_logout(self):
        resp = self.app.get('/rest/auth/logout',
                            headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                     'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)
        self.assertEqual(resp_json,
                         {'success': {'status': 'ok'}},
                         resp_json)

    def test_fake_logout(self):
        resp = self.app.get('/rest/auth/logout',
                            headers={'Cr-Token': 'PREDEFINED_TOKEN'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)
        self.assertEqual(resp_json, {'error': {'msg': 'Cannot logout'}})
