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

from mock import Mock

from cloudrunner_server.dispatcher.server import Dispatcher
import cloudrunner.core.message as M
from cloudrunner_server.tests import base


class TestServer(base.BaseTestCase):

    def test_list_active_nodes(self):
        disp = Dispatcher('run', config=base.CONFIG)
        disp.init_libs()
        self.assertIsNotNone(disp.transport_class)
        disp.backend = Mock()
        node1 = Mock()
        node1.name = "node1"
        node1.last_seen = 100
        node2 = Mock()
        node2.name = "node2"
        node2.last_seen = 1
        tenant = Mock()
        tenant.active_nodes = lambda: iter([node1, node2])
        disp.backend.tenants.get.return_value = tenant

        msg = disp.list_active_nodes(org='MyOrg')
        self.assertTrue(isinstance(msg, M.Nodes))
        self.assertEquals(msg.nodes[0]['name'], node1.name)
        self.assertEquals(msg.nodes[0]['last_seen'], node1.last_seen)
        self.assertEquals(msg.nodes[1]['name'], node2.name)
        self.assertEquals(msg.nodes[1]['last_seen'], node2.last_seen)
