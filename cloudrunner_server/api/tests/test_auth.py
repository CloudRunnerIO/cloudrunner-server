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
from mock import Mock
from mock import patch
import webtest

from cloudrunner_server.api.tests import base


class TestAuthentication(base.BaseRESTTestCase):

    @patch('cloudrunner_server.plugins.auth.user_db.random_token',
           Mock(return_value="A_SECRET_TOKEN"))
    def test_login(self):
        now = datetime.now()
        resp = self.app.get('/rest/auth/login/testuser/testpassword')
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)['login']
        resp_json['expire'] = parser.parse(resp_json['expire'])
        resp_json['expire'] = resp_json['expire'].replace(microsecond=0)

        exact_exp = now + timedelta(minutes=1440)
        self.assertEqual(resp_json['user'], 'testuser')
        self.assertEqual(len(resp_json['token']), len("A_SECRET_TOKEN"))
        self.assertEqual(abs((exact_exp - resp_json['expire']).seconds), 0)
        self.assertEqual(resp_json['token'], 'A_SECRET_TOKEN')

    def test_fake_login(self):
        resp = self.app.get('/rest/auth/login/testuser/wrong_password')
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)['login']

        self.assertEqual(resp_json, dict(error="Cannot login"))

    def test_unauthorized_call(self):
        with self.assertRaises(webtest.app.AppError):
            self.app.get('/rest/library/workflows',
                         headers={'Cr-Token': 'NON_EXISTING_TOKEN',
                                  'Cr-User': 'testuser'})

    def test_logout(self):
        resp = self.app.get('/rest/auth/logout',
                            headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                     'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)
        self.assertEqual(resp_json,
                         {'status': 'ok'},
                         resp_json)

    def test_fake_logout(self):
        resp = self.app.get('/rest/auth/logout',
                            headers={'Cr-Token': 'PREDEFINED_TOKEN'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)
        self.assertEqual(resp_json, {'error': 'Cannot logout'}, resp_json)
