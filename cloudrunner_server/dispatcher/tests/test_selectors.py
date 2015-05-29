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
from mock import Mock, patch

from cloudrunner.core import parser
from cloudrunner_server.tests import base

SESSION = "1234-5678-9012"


class TestSelectors(base.BaseTestCase):

    def test_dispatcher(self):
        from cloudrunner_server.dispatcher import server, TaskQueue
        disp = server.Dispatcher('run', config=base.CONFIG)
        disp.init_libs()
        self.assertIsNotNone(disp.transport_class)
        disp.user_id = 'some_user'
        disp.user_token = 'some_token'
        disp.auth_type = 2

        script = """
#! switch [*]
test_1
export NEXT_NODE='host2'

#! switch [$NEXT_NODE] --plugin-dir
hostname

export next_step='linux'

#! switch [os=$next_step]
whoami
"""

        class Task(object):
            pass
        queue = TaskQueue()
        task = Task()
        task.session_id = '1234-5678-9012'
        task.owner = 'user'
        queue.tasks.append(task)

        disp.manager = Mock(prepare_session=lambda *args, **kwargs: queue)

        env = {'KEY': 'VALUE'}
        access_map = {'org': 'DEFAULT', 'roles': {'*': '@'}}
        with nested(
            patch.multiple(parser,
                           parse_selectors=Mock(
                               side_effect=[
                                   (None, ''), ("*", ''),
                                   (None, ''), ("$NEXT_NODE", ''), (None, ''),
                                   ("os=$next_step", ''), (None, '')
                               ]
                           )),
            patch('uuid.uuid4',
                  Mock(return_value=Mock(
                       hex='416728b252a411e3ae1600247e6dff02'))),
            patch('time.time', Mock(return_value=1385031137))
        ):
            deployment_id = 2
            tasks = [{'body': script, 'target': '*'}]
            ret = disp.dispatch('user_id',
                                deployment_id,
                                tasks,
                                access_map,
                                env=env)
            """
            expected = [call('\n'),  # noqa
                        call('#! switch [*]'),
                        call('\ntest_1\nexport NEXT_NODE=\'host2\'\n\n'),
                        call('#! switch [$NEXT_NODE] --plugin-dir'),
                        call('\nhostname\n\nexport next_step=\'linux\'\n\n'),
                        call('#! switch [os=$next_step]'),
                        call('\nwhoami\n')]
            """
            self.assertTrue(ret.tasks[0].session_id, '1234-5678-9012')

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
                self.backend = Mock()
                self.register_session = Mock()
                self.config = Mock()

        remote_user_map = {'org': 'DEFAULT', 'roles': {'*': '@'}}
        ctx = Ctx()

        class PluginCtx(object):

            def __init__(self):
                self.args_plugins = []
                self.lib_plugins = []
                self.job_plugins = []

        env = {'NEXT_NODE': ['host2', 'host9']}
        queue = Mock(return_value=Mock(get=lambda *args: [env, None]))
        task_id = 101
        step_id = 0
        from cloudrunner_server.dispatcher.session import JobSession
        session = JobSession(
            ctx, 'user', SESSION, task_id, step_id,
            {'target': '*', 'body': "\ntest_1\nexport NEXT_NODE='host2'\n\n"},
            remote_user_map, queue(), queue(), None, None)
        session._reply = Mock()

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

            """
            expected = [
                call('*',
                     {'remote_user_map': remote_user_map,
                      'attachments': [],
                      'env': {'NEXT_NODE': ['host2', 'host9']},
                      'script': "\ntest_1\nexport NEXT_NODE='host2'\n\n"},
                     timeout=120)]

            self.assertEqual(
                ctx.register_session.call_args_list, [call("1234-5678-9012")])

            #self.assertEqual(
            #    session._reply.call_args_list[0], expected[0])
            """
