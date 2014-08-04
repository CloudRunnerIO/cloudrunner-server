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

from cloudrunner_server.master.functions import CertController
from cloudrunner_server.plugins.auth.user_db import AuthDb
from cloudrunner_server.dispatcher.server import Dispatcher
from cloudrunner_server.tests import base


class TestServer(base.BaseTestCase):

    def test_list_nodes(self):
        disp = Dispatcher('run', config=base.CONFIG)
        disp.init_libs()
        self.assertIsNotNone(disp.auth)
        self.assertIsNotNone(disp.transport_class)

        CertController.get_approved_nodes = Mock(return_value=['node1',
                                                               'node2'])
        remote_user_map = Mock()
        remote_user_map.org = Mock(return_value='MyOrg')
        self.assertEqual(
            disp.list_nodes('', remote_user_map), (True, ['node1', 'node2']))

    def test_scheduler(self):
        disp = Dispatcher('run', config=base.CONFIG)
        disp.init_libs()
        user = 'userX'
        disp.user_id = user
        user_token = "user_token"
        disp.user_token = user_token
        remote_user_map = Mock()
        remote_user_map.org = Mock(return_value='MyOrg')
        with patch(
            'cloudrunner_server.plugins.auth.user_db.UserMap.authenticate',
                Mock(return_value=(True, {'*': 'root'}))):
            disp._login()
            self.assertIsNotNone(disp.auth)
            self.assertIsNotNone(disp.transport_class)

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
                    patch(
                    'cloudrunner_server.dispatcher.server.'
                    'Dispatcher.get_api_token',
                    Mock(return_value=['TOKEN', 'SOME_GENERATED_TOKEN'])),
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

    def test_login(self):
        disp = Dispatcher('run', config=base.CONFIG)

        with nested(
            patch.multiple(AuthDb,
                           __init__=Mock(return_value=None),
                           authenticate=Mock(return_value=[True, '123']),
                           validate=Mock(return_value=[True, '123'])),
                patch('datetime.datetime', now=Mock(return_value=333333333))):
            disp.init_libs()
            self.assertIsNotNone(disp.auth)
            self.assertIsNotNone(disp.transport_class)
            disp.user_id = 'some_user'
            disp.user_token = 'some_token'

            auth = disp._login(auth_type=1)
            self.assertEqual((auth[0], str(auth[1])), (True, '123'))

            disp.user_token = 'some_token'
            auth = disp._login(auth_type=2)
            self.assertEqual((auth[0], str(auth[1])), (True, '123'))

    def test_get_token(self):
        disp = Dispatcher('run', config=base.CONFIG)

        with nested(
            patch.multiple(AuthDb,
                           __init__=Mock(return_value=None),
                           get_token=Mock(
                               return_value=(
                                   'some_user', '1' * 60, 'MyOrg')),
                           authenticate=Mock(return_value=[True, '123']),
                           validate=Mock(return_value=[True, '123'])),
                patch('random.choice', Mock(return_value='1'))):
            disp.init_libs()
            self.assertIsNotNone(disp.auth)
            self.assertIsNotNone(disp.transport_class)
            disp.user_id = 'some_user'
            disp.user_token = 'some_token'
            disp.auth_type = 2

            self.assertEqual(disp.get_api_token('xxx', {}),
                             ['TOKEN', '1' * 60, 'MyOrg'])
