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
from mock import call, Mock, patch

from cloudrunner_server.tests import base

SESSION = "1234-5678-9012"


class TestDispatch(base.BaseTestCase):

    def test_session(self):

        from cloudrunner_server.dispatcher.session import JobSession

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
                self.backend = Mock()

                self.config = Mock()
                self.publisher = Mock()
                self.register_session = Mock()

        remote_user_map = {'org': 'DEFAULT', 'roles': {'*': '@'}}

        ctx = Ctx()

        class PluginCtx(object):

            def __init__(self):
                self.args_plugins = []
                self.lib_plugins = []
                self.job_plugins = []

        env = {'NEXT_NODE': ['host2', 'host9']}
        queue = Mock(return_value=Mock(get=lambda *args: [env, None]))

        session = JobSession(
            ctx, 'user', SESSION,
            {'target': '*', 'body': "\ntest_1\nexport NEXT_NODE='host2'\n\n"},
            remote_user_map, queue(), queue(), None, None)

        session._reply = Mock()
        session._create_ts = Mock(return_value=123456789.101)
        ret_data1 = [
            ['PIPE', 'JOB_ID', 123456789.101, 'admin',
                'NODE1', '["STDOUT", "BLA"]'],
            [
                'JOB_ID', [{'node': "NODE1",
                            'remote_user': 'root',
                            'ret_code': 1,
                            'env': {'NEXT_NODE': "host2"}},
                           {'node': "NODE6",
                            'remote_user': 'root',
                            'ret_code': 1,
                            'env': {'NEXT_NODE': "host9"}}],
                []
            ]
        ]
        with nested(
                patch.multiple(session,
                               read=Mock(side_effect=[iter(ret_data1)]))):
            session.run()

            expected = [
                {'hdr': {}, 'ts': 123456789.101,
                 'session_id': '1234-5678-9012', 'kw':
                 ['org', 'user', 'session_id', 'ts'],
                 'user': 'user', 'org': 'DEFAULT'},
                {'node': 'NODE1',
                 'hdr': {},
                 'kw': ['node', 'stdout', 'run_as', 'ts',
                        'session_id', 'user', 'org'],
                 'stdout': '["STDOUT", "BLA"]',
                 'run_as': 'admin',
                 'ts': 123456789.101,
                 'session_id': 'JOB_ID',
                 'user': 'user', 'org': 'DEFAULT'},
                {'hdr': {}, 'ts': 123456789.101, 'session_id': 'JOB_ID',
                 'kw': ['ts', 'session_id', 'user', 'env',
                        'org', 'result'],
                 'user': 'user', 'env': {'NEXT_NODE': ['host2', 'host9']},
                 'org': 'DEFAULT', 'result': {
                     'NODE1': {'remote_user': 'root', 'ret_code': 1},
                     'NODE6': {'remote_user': 'root', 'ret_code': 1}}}]
            self.assertEqual(
                ctx.register_session.call_args_list, [call("1234-5678-9012")])

            self.assertEqual(
                vars(session._reply.call_args_list[0][0][0]), expected[0])
            self.assertEqual(
                vars(session._reply.call_args_list[1][0][0]), expected[1])
            self.assertEqual(
                vars(session._reply.call_args_list[2][0][0]), expected[2])
