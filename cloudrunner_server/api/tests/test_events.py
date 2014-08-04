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

# from mock import patch, MagicMock

from cloudrunner_server.api.tests import base


class TestEvents(base.BaseRESTTestCase):

    # @patch('cloudrunner_server.api.v0_9.controllers.events.Event.next')
    def test_get(self):
        cr_data = """id: 100
event: Event123
data: 123
data: 456
data: 789"""

        resp = self.app.get('/rest/events/get', headers={
            'Cr-Token': 'PREDEFINED_TOKEN',
            'Cr-User': 'testuser',
            'Last-Event-Id': '100'})

        self.assertEqual(resp.status_int, 200, resp.status_int)
        self.assertEqual(resp.content_type, 'text/event-stream',
                         resp.content_type)
        print cr_data
        # self.assertEqual(resp.body, cr_data, resp.body)
