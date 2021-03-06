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
from mock import MagicMock


class TestEvents(base.BaseRESTTestCase):

    def test_get(self):
        sse_data = """id: 10
retry: 1000
event: 1234567
data: 1234567

"""
        self.aero.check = MagicMock(return_value=10)

        resp = self.app.get('/rest/status/get?1234567', headers={
            'Cr-Token': 'PREDEFINED_TOKEN',
            'Cr-User': 'testuser',
            'Last-Event-Id': '100'})

        self.assertEqual(resp.status_int, 200, resp.status_int)
        self.assertEqual(resp.content_type, 'text/event-stream',
                         resp.content_type)
        self.assertEqual(resp.body, sse_data)
