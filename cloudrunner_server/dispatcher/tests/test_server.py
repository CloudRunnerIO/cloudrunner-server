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
from mock import Mock
from mock import DEFAULT
from mock import call
from mock import patch
import os
import sys
import tempfile
import uuid
from crontab import CronTab

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
        with patch('cloudrunner.plugins.auth.user_db.UserMap.authenticate',
                   Mock(return_value=(True, {'*': 'root'}))):
            disp._login()
            self.assertIsNotNone(disp.auth)
            self.assertIsNotNone(disp.transport_class)

        # Add
        cron_obj = Mock()
        cron_obj.is_valid = Mock(return_value=True)
        cron_obj.set_slices = Mock()
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
                    'cloudrunner.dispatcher.server.Dispatcher.get_api_token',
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
                                   '/usr/bin/cloudrunner'))):
                with patch.multiple(cron_scheduler.CronScheduler,
                                    job_dir='/tmp',
                                    _all=Mock(return_value=[job1]),
                                    crontab=Mock(
                                    __iter__=Mock(
                                    return_value=iter(
                                    ['job1', 'job2']))),
                                    create=True):
                    # List
                    self.assertEqual(disp.schedule('', {}, action="list"),
                                    (True, [
                                     {'enabled': True, 'name': 'job1',
                                         'period': '', 'user': 'user'}]))
                with patch.multiple(cron_scheduler.CronScheduler,
                                    job_dir='/tmp',
                                    _all=Mock(return_value=[]),
                                    crontab=Mock(
                                    __iter__=Mock(
                                    return_value=iter(
                                    ['job1', 'job2']))),
                                    create=True):
                    self.assertEqual(disp.schedule('cron_content', {},
                                                   period="/2 * * * *",
                                                   name="my_cron", action="add"),
                                    (True, None))

                CronTab.new.assert_called_with(
                    comment=meta,
                    command='/usr/bin/cloudrunner-master schedule run %s' %
                    str(uuid.uuid1()))
                cron_obj.set_slices.assert_called_with(
                    ['/2', '*', '*', '*', '*'])
                os.write.assert_called_with('file', 'cron_content')

            # View
            with nested(patch('crontab.CronTab.__iter__',
                        Mock(return_value=iter([cron_job]))),
                        patch('os.read', Mock(return_value="Cron content")),
                        patch('sys.argv',
                              Mock(__getitem__=lambda *args: '/usr/bin/'))):
                self.assertEqual(disp.schedule('', {}, name='my_cron',
                                               action="view"),
                                (True, {'job_id': str(uuid.uuid1()),
                                        'name': 'my_cron',
                                        'period': 0,
                                        'owner': 'userX',
                                        'content': "Cron content"}))

            # Delete
            with patch('crontab.CronTab.__iter__',
                       Mock(return_value=iter([cron_job]))):
                self.assertEqual(disp.schedule('', {}, name='my_cron',
                                               action="delete"),
                                 (True, 'Cron job my_cron removed'))

            # Execute
            with patch('crontab.CronTab.__iter__',
                       Mock(return_value=iter([cron_job]))):
                self.assertEqual(disp.schedule('', {}, name='my_cron',
                                               action="delete"),
                                 (True, 'Cron job my_cron removed'))

    def test_login(self):
        disp = Dispatcher('run', config=base.CONFIG)

        auth_db_mock = Mock()
        cursor_mock = Mock()
        row_mock = Mock()
        elem_mock = Mock()
        elem_mock.__getitem__ = Mock(return_value=2)
        row_mock.fetchone = Mock(return_value=elem_mock)
        cursor_mock.execute = Mock(return_value=row_mock)
        auth_db_mock.cursor = Mock(return_value=cursor_mock)

        with nested(patch('sqlite3.connect', Mock(return_value=auth_db_mock)),
                    patch('datetime.datetime', now=Mock(return_value=333333333))):
            disp.init_libs()
            self.assertIsNotNone(disp.auth)
            self.assertIsNotNone(disp.transport_class)
            disp.user_id = 'some_user'
            disp.user_token = 'some_token'

            row_mock.fetchall = Mock(return_value=iter([('*', 'root'),
                                    ('.*-win', 'admin')]))
            auth = disp._login(auth_type=1)
            self.assertEqual((auth[0], str(auth[1])),
                            (True, 'some_user:[root]:.*-win:admin'))

            row_mock.fetchall = Mock(return_value=iter([('*', 'root'),
                                    ('.*-win', 'admin')]))

            auth = disp._login(auth_type=2)
            self.assertEqual((auth[0], str(auth[1])),
                            (True, 'some_user:[root]:.*-win:admin'))

            self.assertEqual(cursor_mock.execute.call_args_list,
                             [call('SELECT count(*) FROM Users'),
                              call(
                              'SELECT Users.id FROM Users INNER JOIN Organizations org ON Users.org_uid = org.org_uid WHERE username = ? AND token = ? AND active = 1',
                            ('some_user', 'some_token')),
                                 call('SELECT count(*) FROM Users'),
                                 call(
                                     'SELECT servers, role FROM AccessMap WHERE user_id = ?', (2,)),
                                 call(
                                     'SELECT org.name FROM Organizations org INNER JOIN Users ON org.org_uid = Users.org_uid WHERE org.active = 1 and Users.id = ?', (2,)),
                                 call('SELECT count(*) FROM Users'),
                                 call(
                                     'SELECT user_id FROM Tokens INNER JOIN Users ON Users.id = Tokens.user_id WHERE username = ? AND Tokens.token = ? AND expiry > ?',
                                     ('some_user', 'some_token', 333333333)),
                                 call('SELECT count(*) FROM Users'),
                                 call(
                                     'SELECT servers, role FROM AccessMap WHERE user_id = ?', (2,)),
                                 call('SELECT org.name FROM Organizations org INNER JOIN Users ON org.org_uid = Users.org_uid WHERE org.active = 1 and Users.id = ?', (2,))]
            )

    def test_get_token(self):
        disp = Dispatcher('run', config=base.CONFIG)

        auth_db_mock = Mock()
        cursor_mock = Mock()
        row_mock = Mock()
        elem_mock = Mock()
        elem_mock.__getitem__ = Mock(return_value=2)
        row_mock.fetchone = Mock(return_value=elem_mock)
        cursor_mock.execute = Mock(return_value=row_mock)
        auth_db_mock.cursor = Mock(return_value=cursor_mock)

        date_mock = Mock(return_value=datetime.now())
        with nested(patch('sqlite3.connect', Mock(return_value=auth_db_mock)),
                    patch('random.choice', Mock(return_value='1'))):
            disp.init_libs()
            self.assertIsNotNone(disp.auth)
            self.assertIsNotNone(disp.transport_class)
            disp.user_id = 'some_user'
            disp.user_token = 'some_token'

            self.assertEqual(disp.get_api_token('', {}),
                             ['TOKEN', '1' * 60])
