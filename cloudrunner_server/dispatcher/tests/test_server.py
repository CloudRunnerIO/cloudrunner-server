#!/usr/bin/python
# -*- coding: utf-8 -*-
# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2013 CloudRunner.IO
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from contextlib import nested
from datetime import datetime
from mock import Mock, MagicMock
from mock import DEFAULT
from mock import call
from mock import patch
import os
import sys
import tempfile
import uuid
from crontab import CronTab

from cloudrunner.util.crypto import hash_token
from cloudrunner_server.master.functions import CertController
from cloudrunner_server.plugins.auth.user_db import UserMap
from cloudrunner_server.plugins.auth.user_db import AuthDb
from cloudrunner_server.dispatcher.server import Dispatcher
from cloudrunner_server.dispatcher.server import CONFIG
from cloudrunner_server.plugins.scheduler import cron_scheduler
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
        self.assertEqual(disp.list_nodes('', remote_user_map),
                        (True, ['node1', 'node2']))

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

        with nested(patch('uuid.uuid1', Mock(return_value=123123)),
                    patch.multiple('os', write=DEFAULT, close=DEFAULT,
                                   unlink=DEFAULT, stat=DEFAULT),
                    patch('tempfile.mkstemp',
                    Mock(return_value=('file', 'cron_file'))),
                    patch.multiple('crontab.CronTab', read=Mock(),
                                   write=Mock(), remove=Mock(),
                                   new=Mock(return_value=cron_obj)),
                    patch(
                    'cloudrunner_server.dispatcher.server.Dispatcher.get_api_token',
                    Mock(return_value=['TOKEN', 'SOME_GENERATED_TOKEN'])),
                    patch('__builtin__.open',
                          return_value=Mock(
                          read=Mock(return_value='Cron content')))):
            meta = '%(user)s\t%(token)s\t%(job_id)s\t%(name)s\t%(file)s\t' % \
                dict(user=user, token='SOME_GENERATED_TOKEN',
                     job_id=str(uuid.uuid1()),
                     name='my_cron', file='cron_file')

            job1 = Mock(return_value=None, user='user',
                        enabled=True, period='* * * * *',
                        time='', create=True)
            job1.name = 'job1'
            job2 = Mock(return_value=None, user='user',
                        enabled=True, period='* * * * *',
                        time='', create=True)
            job2.name = 'job2'
            with nested(patch('crontab.CronTab',
                              __iter__=Mock(return_value=iter([cron_job])),
                              __getitem__=Mock(return_value=cron_job)),
                        patch('sys.argv',
                              Mock(__getitem__=lambda *args:
                                   '/usr/bin/cloudrunner')),
                        patch('cloudrunner_server.dispatcher.PluginContext',
                              return_value=Mock(create_auth_token=lambda *args,
                                                **kwargs: "SOME_GENERATED_TOKEN"))):
                with patch.multiple(cron_scheduler.CronScheduler,
                                    job_dir='/tmp',
                                    _own=Mock(return_value=[job1]),
                                    crontab=Mock(
                                    __iter__=Mock(
                                    return_value=iter(
                                    ['job1', 'job2']))),
                                    create=True):
                    # List
                    self.assertEqual(disp.plugin("", remote_user_map,
                                                 plugin='scheduler',
                                                 args="list --json"),
                                     [(True, [
                                     {'enabled': True, 'name': 'job1',
                                         'period': '', 'user': 'user'}])])
                with patch.multiple(cron_scheduler.CronScheduler,
                                    job_dir='/tmp',
                                    _own=Mock(return_value=[]),
                                    _all=Mock(return_value=[]),
                                    crontab=Mock(
                                    __iter__=Mock(
                                    return_value=iter(
                                    ['job1', 'job2']))),
                                    create=True):
                    self.assertEqual(disp.plugin("cron_content",
                                                 remote_user_map,
                                                 plugin="scheduler",
                                                 args="add my_cron data /2 * * * *"),
                                     [(True, None)])

                CronTab.new.assert_called_with(
                    comment=meta,
                    command='/usr/bin/cloudrunner-master schedule run %s' %
                    str(uuid.uuid1()))
                cron_obj.setall.assert_called_with(
                    '/2', '*', '*', '*', '*')
                os.write.assert_called_with('file', 'cron_content')

            # View
            cron_job = MagicMock(meta=lambda: meta, enabled=True,
                                 command='command',
                                 period='/2 * * * *',
                                 id='123123',
                                 user='userX')
            cron_job.configure_mock(name='my_cron')

            with nested(patch('crontab.CronTab.__iter__',
                        Mock(return_value=iter([cron_job]))),
                        patch('os.read', Mock(return_value="Cron content")),
                        patch('sys.argv',
                              Mock(__getitem__=lambda *args: '/usr/bin/')),
                        patch.multiple(cron_scheduler.CronScheduler,
                                       job_dir='/tmp',
                                       _own=lambda *args, **kwargs: [cron_job],
                                       crontab=Mock(
                                       __iter__=Mock(
                                       return_value=iter(
                                       ['job1', 'job2']))),
                                       create=True)):

                self.assertEqual(disp.plugin('', remote_user_map,
                                             plugin='scheduler',
                                             args="show my_cron"),
                                 [(True, {'job_id': str(uuid.uuid1()),
                                          'name': 'my_cron',
                                          'period': '/2 * * * *',
                                          'owner': 'userX',
                                          'content': "Cron content"})])

                # Delete
                self.assertEqual(disp.plugin('', remote_user_map,
                                             plugin='scheduler',
                                             args="delete my_cron"),
                                 [(True, 'Cron job my_cron removed')])

    def test_login(self):
        disp = Dispatcher('run', config=base.CONFIG)

        with nested(
            patch.multiple(AuthDb,
                __init__=Mock(return_value=None),
                load=Mock(return_value='some_user:[root]:.*-win:admin'),
                authenticate=Mock(return_value=[True, '123']),
                validate=Mock(return_value=[True, '123'])),
            patch('datetime.datetime', now=Mock(return_value=333333333))):
            disp.init_libs()
            self.assertIsNotNone(disp.auth)
            self.assertIsNotNone(disp.transport_class)
            disp.user_id = 'some_user'
            disp.user_token = 'some_token'

            auth = disp._login(auth_type=1)
            self.assertEqual((auth[0], str(auth[1])),
                            (True, 'some_user:[root]:.*-win:admin'))

            disp.user_token = 'some_token'
            auth = disp._login(auth_type=2)
            self.assertEqual((auth[0], str(auth[1])),
                            (True, 'some_user:[root]:.*-win:admin'))

    def test_get_token(self):
        disp = Dispatcher('run', config=base.CONFIG)

        date_mock = Mock(return_value=datetime.now())
        with nested(
            patch.multiple(AuthDb,
                __init__=Mock(return_value=None),
                get_token=Mock(return_value=('some_user', '111111111111111111111111111111111111111111111111111111111111', 'MyOrg')),
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
