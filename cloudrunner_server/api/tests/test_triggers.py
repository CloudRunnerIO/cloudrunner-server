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

from datetime import datetime
import json
from mock import call, patch, Mock

from cloudrunner_server.api.tests import base
from cloudrunner_server.api.model.triggers import random_token


class TestTriggers(base.BaseRESTTestCase):

    def test_list_jobs(self):
        response = [
            {'name': 'trigger1',
             'script': 'test1',
             'enabled': True,
             'private': False,
             'source': 1,
             'arguments': '* * * * *',
             'owner': 'testuser',
             'path': '/folder1/',
             'id': 1,
             'library': 'cloudrunner'},
            {'name': 'trigger2',
             'script': 'test1',
             'enabled': True,
             'private': False,
             'source': 2,
             'arguments': 'JOB',
             'owner': 'testuser2',
             'path': '/folder2/',
             'id': 2,
             'library': 'private'}
        ]

        resp = self.app.get('/rest/triggers/jobs',
                            headers={
                                'Cr-Token': 'PREDEFINED_TOKEN',
                                'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        for trig in resp_json['triggers']:
            trig.pop('key')
            trig.pop('created_at')
        self.assertEqual(resp_json['triggers'],
                         response, resp_json['triggers'])

    def test_show_job(self):
        resp = self.app.get('/rest/triggers/jobs/1/trigger1', headers={
            'Cr-Token': 'PREDEFINED_TOKEN', 'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        resp_json['job'].pop('created_at')
        self.assertEqual(resp_json['job'], {"name": "trigger1",
                                            "script": "test1",
                                            "enabled": True,
                                            "private": False,
                                            "source": 1,
                                            "arguments": "* * * * *",
                                            "owner": "testuser",
                                            "path": "/folder1/",
                                            "id": 1,
                                            "library": "cloudrunner"},
                         resp.body)

    @patch('cloudrunner_server.api.v0_9.controllers.'
           'triggers.user_manager')
    @patch('cloudrunner_server.api.v0_9.controllers.'
           'triggers.schedule_manager')
    @patch('cloudrunner_server.api.model.triggers.random_token')
    def test_create(self, rand, scheduler, auth):
        rand.return_value = '111111111'
        scheduler.add.return_value = (True, None)
        auth.create_token.return_value = ("JOB_TOKEN", datetime(2020, 10, 1))
        resp = self.app.post('/rest/triggers/jobs',
                             "name=trigger_new&arguments=* 0 * * *&target=/folder1/scr1"  # noqa
                             "&source=1",
                             headers={
                                 'Cr-Token': 'PREDEFINED_TOKEN',
                                 'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        kw = {'exec': 'curl https://localhost/rest/fire/?user=testuser\\&token=JOB_TOKEN'  # noqa
        '\\&trigger=trigger_new\\&key=111111111\\&tags=Scheduler,trigger_new '}  # noqa

        self.assertEqual(resp_json,  {"success": {"status": "ok"}},
                         resp.body)
        self.assertEqual(scheduler.add.call_args_list,
                         [call('testuser',
                               auth_token='JOB_TOKEN',
                               period='* 0 * * *',
                               name='trigger_new',
                               **kw)])
        self.assertRedisInc('triggers.jobs')
        self.assertRedisPub('triggers.jobs', 'create')

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

        self.assertRedisInc('triggers.jobs')
        self.assertRedisPub('triggers.jobs', 'update')

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

        self.assertEqual(resp_json,
                         {"error": {"msg": "Value not present: ''source''",
                         "field": "'source'"}},
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
        self.assertRedisInc('triggers.jobs')
        self.assertRedisPub('triggers.jobs', 'delete')
