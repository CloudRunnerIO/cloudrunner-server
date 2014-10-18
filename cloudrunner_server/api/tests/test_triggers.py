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

import json
from mock import call, patch

from cloudrunner_server.api.tests import base


class TestTriggers(base.BaseRESTTestCase):

    def test_list_jobs(self):
        response = [
            {'name': 'trigger1',
             'script': 'test2',
             'enabled': True,
             'private': False,
             'source': 1,
             'script_dir': 'cloudrunner/folder1/folder11',
             'share_url': None,
             'owner': 'testuser',
             'arguments': '* * * * *',
             'id': 1},
            {'name': 'trigger2',
             'enabled': True,
             'private': False,
             'source': 2,
             'arguments': 'JOB',
             'owner': 'testuser2',
             'share_url': None,
             'script_dir': 'cloudrunner/folder1',
             'script': 'test1',
             'id': 2}
        ]

        resp = self.app.get('/rest/triggers/jobs',
                            headers={
                                'Cr-Token': 'PREDEFINED_TOKEN',
                                'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        for trig in resp_json['triggers']:
            trig.pop('created_at')
        self.assertEqual(resp_json['triggers'],
                         response, resp_json['triggers'])

    def test_show_job(self):
        resp = self.app.get('/rest/triggers/jobs/1/trigger1', headers={
            'Cr-Token': 'PREDEFINED_TOKEN', 'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        resp_json['job'].pop('created_at')
        self.assertEqual(resp_json['job'],
                         {"name": "trigger1",
                          "script": "test2",
                          "enabled": True,
                          "private": False,
                          "source": 1,
                          "script_dir": "cloudrunner/folder1/folder11",
                          "share_url": None,
                          "owner": "testuser",
                          "id": 1,
                          "arguments": "* * * * *"})

    @patch('cloudrunner_server.api.v0_9.controllers.'
           'triggers.schedule_manager')
    @patch('cloudrunner_server.api.model.users.random_token')
    @patch('cloudrunner_server.api.model.triggers.random_token')
    def test_create(self, t_rand, u_rand, scheduler):
        t_rand.return_value = '222222222'
        u_rand.return_value = '111111111'
        scheduler.add.return_value = (True, None)
        resp = self.app.post('/rest/triggers/jobs',
                             "name=trigger_new&arguments=* 0 * * *&target=/folder1/scr1"  # noqa
                             "&source=1",
                             headers={
                                 'Cr-Token': 'PREDEFINED_TOKEN',
                                 'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        url = 'https://localhost/rest/fire/?trigger=trigger_new' \
        '&key=222222222&tags=Scheduler,trigger_new& '  # noqa

        self.assertEqual(resp_json, {"success": {"status": "ok"}},
                         resp.body)
        self.assertEqual(scheduler.add.call_args_list,
                         [call('testuser',
                               'trigger_new',
                               '* 0 * * *',
                               url)])
        self.assertRedisInc('jobs:create')
        self.assertRedisPub('jobs:create', 3)

    @patch('cloudrunner_server.api.v0_9.controllers.'
           'triggers.schedule_manager')
    def test_update(self, scheduler):
        scheduler.edit.return_value = (True, None)

        resp = self.app.patch('/rest/triggers/jobs',
                              "name=trigger1&arguments=* 1 2 3 *",
                              headers={
                                  'Cr-Token': 'PREDEFINED_TOKEN',
                                  'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        self.assertEqual(resp_json, {"success": {"status": "ok"}}, resp.body)
        self.assertEqual(scheduler.edit.call_args_list,
                         [call('testuser',
                               name='trigger1',
                               period='* 1 2 3 *')])

        self.assertRedisInc('jobs:update')
        self.assertRedisPub('jobs:update', 1)

    @patch('cloudrunner_server.api.v0_9.controllers.'
           'triggers.schedule_manager')
    def test_update_fail(self, scheduler):
        scheduler.edit.return_value = (True, None)

        resp = self.app.put('/rest/triggers/jobs',
                            "name=job1",
                            headers={
                                'Cr-Token': 'PREDEFINED_TOKEN',
                                'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        self.assertEqual(scheduler.edit.call_args_list, [])

        self.assertRedisInc(None)
        self.assertRedisPub(None, None)

        self.assertEqual(resp_json, {"error":
                                     {"msg": "Value not present: ''source''",
                                      "field": "'source'"
                                      }},
                         resp.body)

    @patch('cloudrunner_server.api.v0_9.controllers.'
           'triggers.schedule_manager')
    def test_delete_job(self, scheduler):
        scheduler.delete.return_value = (True, None)

        resp = self.app.delete('/rest/triggers/jobs/1',
                               headers={
                                   'Cr-Token': 'PREDEFINED_TOKEN',
                                   'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        # self.assertEqual(scheduler.delete.call_args_list,
        #                 [call('testuser', name='job1')])

        self.assertEqual(resp_json, {"success": {"status": "ok"}}, resp.body)
        self.assertRedisInc('jobs:delete')
        self.assertRedisPub('jobs:delete', 1)
