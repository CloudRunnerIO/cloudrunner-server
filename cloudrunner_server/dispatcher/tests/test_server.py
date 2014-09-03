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

from contextlib import nested
from mock import Mock, MagicMock
from mock import DEFAULT
from mock import patch
import uuid

from cloudrunner_server.dispatcher.server import Dispatcher
from cloudrunner.core.message import Nodes
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

        remote_user_map = Mock()
        remote_user_map.org = Mock(return_value='MyOrg')
        msg = disp.list_active_nodes(remote_user_map)
        self.assertTrue(isinstance(msg, Nodes))
        self.assertEquals(msg.nodes[0]['name'], node1.name)
        self.assertEquals(msg.nodes[0]['last_seen'], node1.last_seen)
        self.assertEquals(msg.nodes[1]['name'], node2.name)
        self.assertEquals(msg.nodes[1]['last_seen'], node2.last_seen)

    def test_scheduler(self):
        disp = Dispatcher('run', config=base.CONFIG)
        disp.init_libs()
        user = 'userX'
        disp.user_id = user
        user_token = "user_token"
        disp.user_token = user_token
        remote_user_map = Mock()
        remote_user_map.org = Mock(return_value='MyOrg')

        # Add
        cron_obj = Mock()
        cron_obj.is_valid = Mock(return_value=True)
        cron_obj.setall = Mock()
        cron_obj.enable = Mock()
        cron_job = Mock(meta=lambda: meta, enabled=True,
                        command=Mock(command=lambda: 'command'),
                        render_time=lambda: 0,
                        name='my_cron')

        with nested(patch('uuid.uuid4', Mock(return_value=Mock(hex="123123"))),
                    patch.multiple('os', write=DEFAULT, close=DEFAULT,
                                   unlink=DEFAULT, stat=DEFAULT),
                    patch('tempfile.mkstemp',
                    Mock(return_value=('file', 'cron_file'))),
                    patch.multiple('crontab.CronTab', read=Mock(),
                                   write=Mock(), remove=Mock(),
                                   new=Mock(return_value=cron_obj)),
                    patch('__builtin__.open',
                          return_value=Mock(read=Mock(
                                            return_value='Cron content')))):
            meta = '%(user)s\t%(token)s\t%(job_id)s\t%(name)s\t%(file)s\t' % \
                dict(user=user, token='SOME_GENERATED_TOKEN',
                     job_id=uuid.uuid4().hex,
                     name='my_cron', file='cron_file')

            job1 = Mock(return_value=None, user='user',
                        enabled=True, period='* * * * *',
                        time='', create=True)
            job1.name = 'job1'
            job2 = Mock(return_value=None, user='user',
                        enabled=True, period='* * * * *',
                        time='', create=True)
            job2.name = 'job2'
            # View
            cron_job = MagicMock(meta=lambda: meta, enabled=True,
                                 command='command',
                                 period='/2 * * * *',
                                 id='123123',
                                 user='userX')
            cron_job.configure_mock(name='my_cron')
