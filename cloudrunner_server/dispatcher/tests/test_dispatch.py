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
from mock import call
from mock import Mock
from mock import patch

from cloudrunner_server.dispatcher.session import JobSession
from cloudrunner_server.tests import base

SESSION = "1234-5678-9012"


class TestDispatch(base.BaseTestCase):

    def test_session(self):

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
                self.config.security = Mock(use_org=False)

        remote_user_map = {'org': 'DEFAULT', 'roles': {'*': '@'}}

        class PluginCtx(object):

            def __init__(self):
                self.args_plugins = []
                self.lib_plugins = []
                self.job_plugins = []

        env = {'NEXT_NODE': ['host2', 'host9']}
        queue = Mock(return_value=Mock(get=lambda *args: [env, None]))

        session = JobSession(
            Ctx(), 'user', SESSION,
            {'target': '*', 'body': "\ntest_1\nexport NEXT_NODE='host2'\n\n"},
            remote_user_map, queue(), queue(), None)

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

        with nested(
            patch.multiple(session,
                           exec_section=Mock(side_effect=[iter(ret_data1)]))):
            session.run()

            expected = [
                call(
                    '*',
                    {'remote_user_map': remote_user_map,
                     'attachments': [],
                     'env': {'NEXT_NODE': ['host2', 'host9']},
                     'script': "\ntest_1\nexport NEXT_NODE='host2'\n\n"},
                    timeout=None)]

            self.assertEqual(
                session.exec_section.call_args_list, expected)
