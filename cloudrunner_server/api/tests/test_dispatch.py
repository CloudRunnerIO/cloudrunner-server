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

ctx_mock = Mock()
sock_mock = Mock()
ctx_mock.socket.return_value = sock_mock


class TestDispatch(base.BaseRESTTestCase):

    @patch('zmq.Context', Mock(return_value=ctx_mock))
    def test_list_active_nodes(self):
        return
        sock_mock.recv_multipart.return_value = [
            json.dumps(([True, [True, ("Node", 15)]]))]
        resp = self.app.get('/rest/dispatch/active_nodes', headers={
            'Cr-Token': 'PREDEFINED_TOKEN', 'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)
        self.assertEqual(resp_json, {'nodes': ['Node', 15]}, resp_json)
