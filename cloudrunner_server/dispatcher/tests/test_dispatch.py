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
from mock import call
from mock import Mock
from mock import DEFAULT
from mock import patch
import os
import threading

from cloudrunner.core import parser
from cloudrunner_server.plugins.auth.user_db import AuthDb
from cloudrunner_server.dispatcher import server
from cloudrunner_server.dispatcher.session import ServerSession
from cloudrunner_server.dispatcher.server import CONFIG
from cloudrunner_server.tests import base

SESSION = "1234-5678-9012"


class TestDispatch(base.BaseTestCase):

    def test_sesson(self):
        payload = """
#! switch [*]
test_1
export NEXT_NODE='host2'

#! switch [$NEXT_NODE] --plugin-dir
hostname

export next_step='linux'

#! switch [os=$next_step]
whoami
"""
        stop_event = threading.Event()

        class Ctx(object):

            def __init__(self):
                self.plugins_ctx = Mock()
                self.plugins_ctx.args_plugins = Mock()
                self.plugins_ctx.args_plugins.parse_known_args = Mock(
                    return_value=([], []))
                self.plugins_ctx.job_plugins = []
                self.plugins_ctx.lib_plugins = []
                self.job_done_uri = "job_done"
                self.context = Mock()

                self.discovery_timeout = 120
                self.wait_timeout = 120
                self.subscriptions = {SESSION: []}
                self.sessions = {SESSION: []}
                self.transport = Mock()
                job = Mock()
                job.receive = Mock(side_effect=[("READY",)])
                self.transport.create_job = Mock(return_value=job)

                self.config = Mock()
                self.config.security = Mock(use_org=False)

        remote_user_map = Mock(org="MyOrg")

        session = ServerSession(
            Ctx(), 1, SESSION, payload, remote_user_map, stop_event)

        ret_data1 = [
            ['PIPE', 'JOB_ID', 'admin', '["STDOUT", "BLA"]'],
            [
                'JOB_ID', [{'node': "NODE1",
                            'remote_user': 'root',
                            'ret_code': 1,
                            'env': {'NEXT_NODE': "host2"}},
                           {'node': "NODE6",
                            'remote_user': 'root',
                            'ret_code': 1,
                            'env': {'NEXT_NODE': "host9"}}]
            ]
        ]
        ret_data2 = [
            ['PIPE', 'JOB_ID', 'admin', '["STDOUT", "RUN 2 OUT"]'],
            [
                'JOB_ID', [{'node': "NODE2",
                            'remote_user': 'admin',
                            'ret_code': 2,
                            'env': {'next_step': 'linux'}},
                           {'node': "NODE4",
                            'remote_user': 'admin',
                            'ret_code': 0,
                            'env': {'next_step': 'windows'}}]
            ]
        ]
        ret_data3 = [
            ['PIPE', 'JOB_ID', 'admin', '["STDOUT", "RUN 3 OUT"]'],
            [
                'JOB_ID', [{'node': "NODE3",
                            'remote_user': 'admin',
                            'ret_code': 2,
                            'env': {'next_step': 'linux'}},
                           {'node': "NODE4",
                            'remote_user': 'admin',
                            'ret_code': 0,
                            'env': {'next_step': 'windows'}}]
            ]
        ]

        ret = [dict(env={'key1': 'value1'},
                    ret_code=0,
                    node="NODE1",
                    remote_user="remote_user")]
        with nested(
            patch.multiple(session,
                           exec_section=Mock(side_effect=[iter(ret_data1),
                                                          iter(ret_data2),
                                                          iter(ret_data3),
                                                          ]))):
            session.run()

            expected = [call(
                '*', {'libs': [], 'remote_user_map': remote_user_map,
                'env': {'next_step': ['linux', 'windows'],
                'NEXT_NODE': ['host2', 'host9']},
                'script': "\ntest_1\nexport NEXT_NODE='host2'\n\n"}, timeout=None),
                call(
                    'host2 host9', {'libs': [], 'remote_user_map': remote_user_map,
                    'env': {'next_step': ['linux', 'windows'],
                    'NEXT_NODE': ['host2', 'host9']},
                    'script': "\nhostname\n\nexport next_step='linux'\n\n"}, timeout=None),
                call('os=linux os=windows', {'libs': [],
                                             'remote_user_map': remote_user_map,
                                             'env': {'next_step': ['linux', 'windows'],
                                                     'NEXT_NODE': ['host2', 'host9']},
                                             'script': '\nwhoami\n'}, timeout=None)]

            self.assertEqual(
                session.exec_section.call_args_list, expected,
                session.exec_section.call_args_list)
