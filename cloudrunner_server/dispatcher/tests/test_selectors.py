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
import threading

from cloudrunner.core import parser
from cloudrunner_server.dispatcher import server, TaskQueue
from cloudrunner_server.dispatcher.session import JobSession
from cloudrunner_server.tests import base

SESSION = "1234-5678-9012"


class TestSelectors(base.BaseTestCase):

    def test_dispatcher(self):
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
            tasks = [{'body': script, 'target': '*'}]
            ret = disp.dispatch('user_id',
                                tasks,
                                access_map,
                                env=env)
            expected = [call('\n'),  # noqa
                        call('#! switch [*]'),
                        call('\ntest_1\nexport NEXT_NODE=\'host2\'\n\n'),
                        call('#! switch [$NEXT_NODE] --plugin-dir'),
                        call('\nhostname\n\nexport next_step=\'linux\'\n\n'),
                        call('#! switch [os=$next_step]'),
                        call('\nwhoami\n')]

            self.assertTrue(ret.tasks[0].session_id, '1234-5678-9012')

    def _test_returns(self):
        access_map = []
        expected = [  # noqa
            call('*', {'libs': [], 'remote_user_map': access_map,
                       'env': {'next_step': ['linux', 'windows'],
                               'NEXT_NODE': ['host2', 'host9'],
                               'KEY': 'VALUE'},
                       'script':
                       '\ntest_1\nexport NEXT_NODE=\'host2\'\n\n'},
                 timeout=200),
            call(
                'host2 host9', {'libs': [], 'remote_user_map': access_map,
                                'env': {'next_step': ['linux', 'windows'],
                                        'NEXT_NODE': ['host2', 'host9'],
                                        'KEY': 'VALUE'},
                                'script':
                                '\nhostname\n\nexport '
                                'next_step=\'linux\'\n\n'},
                timeout=200),
            call(
                'os=linux os=windows', {
                    'libs': [],
                    'remote_user_map': access_map,
                    'env': {
                        'next_step': ['linux', 'windows'],
                        'NEXT_NODE': ['host2', 'host9'],
                        'KEY': 'VALUE'},
                    'script': '\nwhoami\n'},
                timeout=200)]
        """
        self.assertTrue(disp.publisher.send.call_args_list == expected,
                        disp.publisher.send.call_args_list)
        """

        expected_resp = [  # noqa
            {'nodes': [{'run_as': 'root', 'node': 'NODE1', 'ret_code': 1},
                       {'run_as': 'root', 'node': 'NODE6', 'ret_code': 1}],
                'args': [], 'targets': '*', 'jobid': 'JOB_ID'},
            {'nodes': [{'run_as': 'admin', 'node': 'NODE2', 'ret_code': 2},
                       {'run_as': 'admin', 'node': 'NODE4', 'ret_code': 0}],
                'args': [], 'targets': 'host2 host9', 'jobid': 'JOB_ID'},
            {'nodes': [{'run_as': 'admin', 'node': 'NODE3', 'ret_code': 0}],
             'args': [], 'targets': 'os=linux os=windows', 'jobid': 'JOB_ID'}]

        _ = [call(['PART', '1385031137', '', 'some_user', 'admin',  # noqa
                   '"[\\"TAG1\\", \\"TAG2\\"]"',
                   '416728b2-52a4-11e3-ae16-00247e6dff02',
                   'JOB_ID', '["admin", "[\\"STDOUT\\", \\"BLA\\"]"]']),
             call([
                  'PART', '1385031137', '',
                  'some_user', 'admin', '"[\\"TAG1\\", \\"TAG2\\"]"',
                  '416728b2-52a4-11e3-ae16-00247e6dff02',
                  'JOB_ID', '["admin", "[\\"STDOUT\\", \\"RUN 2 OUT\\"]"]']),
             call([
                  'PART', '1385031137', '', 'some_user', 'admin',
                  '"[\\"TAG1\\", \\"TAG2\\"]"',
                  '416728b2-52a4-11e3-ae16-00247e6dff02', 'JOB_ID',
                  '["admin", "[\\"STDOUT\\", \\"RUN 3 OUT\\"]"]']),
             call([
                  'END', '1385031137', '', 'some_user',
                  '"[\\"TAG1\\", \\"TAG2\\"]"',
                  '416728b2-52a4-11e3-ae16-00247e6dff02',
                  '"\\n#! switch [*]\\ntest_1\\nexport '
                  'NEXT_NODE=\'host2\'\\n\\n'
                  '#! switch [$NEXT_NODE] --plugin-dir\\nhostname\\n\\n'
                  'export next_step=\'linux\'\\n\\n#! switch '
                  '[os=$next_step]\\nwhoami\\n"',
                  '[{"nodes": [{"run_as": "root", "node": "NODE1", '
                  '"ret_code": 1}, {"run_as": "root", "node": "NODE6", '
                  '"ret_code": 1}], "args": [], "targets": "*", '
                  '"jobid": "JOB_ID"}, '
                  '{"nodes": [{"run_as": "admin", "node": "NODE2", '
                  '"ret_code": 2}, {"run_as": "admin", "node": "NODE4", '
                  '"ret_code": 0}], "args": [], "targets": "host2 host9", '
                  '"jobid": "JOB_ID"}, {"nodes": [{"run_as": "admin", "node": '
                  '"NODE3", "ret_code": 0}], "args": [], '
                  '"targets": "os=linux os=windows", "jobid": "JOB_ID"}]'])]

    def test_session(self):
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
                self.backend = Mock()

                self.config = Mock()
                self.config.security = Mock(use_org=False)

        remote_user_map = {'org': 'DEFAULT', 'roles': {'*': '@'}}

        class PluginCtx(object):

            def __init__(self):
                self.args_plugins = []
                self.lib_plugins = []
                self.job_plugins = []

        session = JobSession(
            Ctx(), 'user', SESSION,
            {'target': '*', 'body': "\ntest_1\nexport NEXT_NODE='host2'\n\n"},
            remote_user_map, Mock(), Mock(), None)

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
                call('*',
                     {'remote_user_map': remote_user_map,
                      'attachments': [],
                      'env': {'NEXT_NODE': ['host2', 'host9']},
                      'script': "\ntest_1\nexport NEXT_NODE='host2'\n\n"},
                     timeout=None)]

            self.assertEqual(
                session.exec_section.call_args_list, expected)
