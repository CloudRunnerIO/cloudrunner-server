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
from mock import call
from mock import patch

from cloudrunner_server.api.tests import base


class TestTriggers(base.BaseRESTTestCase):

    @patch('cloudrunner_server.api.v0_9.controllers.triggers.sig_manager')
    def test_list_triggers(self, signals):
        signals.list.return_value = (True, [
            {
                "auth": "True",
                "is_link": "True",
                "signal": "BEST",
                "target": "http://site.com",
                "user": "cloudr"
            },
            {
                "auth": "True",
                "is_link": "True",
                "signal": "TEST",
                "target": "http://site.com",
                "user": "cloudr"
            }
        ])

        resp = self.app.get('/rest/triggers/bindings',
                            headers={
                                'Cr-Token': 'PREDEFINED_TOKEN',
                                'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        self.assertEqual(signals.list.call_args_list,
                         [call(('testuser', 'MyOrg'))])
        self.assertEqual(resp_json['triggers'],
                         signals.list.return_value[1])

    @patch('cloudrunner_server.api.v0_9.controllers.triggers.sig_manager')
    def test_attach_signal(self, signals):
        signals.attach.return_value = (True, None)
        resp = self.app.post('/rest/triggers/bindings',
                             "signal=SIG&target=TGT",
                             headers={
                                 'Cr-Token': 'PREDEFINED_TOKEN',
                                 'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        self.assertEqual(signals.attach.call_args_list,
                         [call(('testuser', 'MyOrg'), 'SIG', 'TGT', None)])

        self.assertRedisInc('triggers.binding')
        self.assertRedisPub('triggers.binding', 'attach')

        self.assertEqual(resp_json, {'status': 'ok'}, resp.body)

    @patch('cloudrunner_server.api.v0_9.controllers.triggers.sig_manager')
    def test_detach_signal(self, signals):
        signals.detach.return_value = (True, None)
        resp = self.app.put('/rest/triggers/bindings/',
                            "signal=SIG&target=http://target", headers={
                                'Cr-Token': 'PREDEFINED_TOKEN',
                                'Cr-User': 'testuser'
                            })
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        self.assertRedisInc('triggers.binding')
        self.assertRedisPub('triggers.binding', 'detach')

        self.assertEqual(signals.detach.call_args_list,
                         [call(('testuser', 'MyOrg'), 'SIG', 'http://target')])
        self.assertEqual(resp_json, {'status': 'ok'}, resp.body)

    @patch('cloudrunner_server.api.v0_9.controllers.triggers.sig_manager')
    def test_detach_signal_fake(self, signals):
        signals.detach.return_value = (False, "Signal not detached")
        resp = self.app.put('/rest/triggers/bindings/',
                            "signal=SIG&target=http://target",
                            headers={
                                'Cr-Token': 'PREDEFINED_TOKEN',
                                'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        self.assertRedisInc(None)
        self.assertRedisPub(None, None)

        self.assertEqual(signals.detach.call_args_list,
                         [call(('testuser', 'MyOrg'), 'SIG', 'http://target')])
        self.assertEqual(resp_json,
                         {'error': "Signal not detached"}, resp.body)
