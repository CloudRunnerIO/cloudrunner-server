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
from mock import call
from mock import patch

from cloudrunner_server.api.tests import base


class TestScheduler(base.BaseRESTTestCase):

    @patch('cloudrunner_server.api.v0_9.controllers.'
           'scheduler.schedule_manager')
    def test_list_jobs(self, scheduler):

        scheduler.list.return_value = (
            True,
            [
                {'user': u'cloudr', 'enabled': True,
                 'period': '0,15,30,45 * * * *', 'name': u'job1'},
                {'user': u'cloudr', 'enabled': True,
                 'period': '@hourly', 'name': u'job2'},
                {'user': u'cloudr', 'enabled': True,
                 'period': '@hourly', 'name': u'job3'}
            ]
        )

        resp = self.app.get('/rest/scheduler/jobs',
                            headers={
                                'Cr-Token': 'PREDEFINED_TOKEN',
                                'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        self.assertEqual(resp_json['jobs'],
                         scheduler.list.return_value[1],
                         resp.body)

    @patch('cloudrunner_server.api.v0_9.controllers.'
           'scheduler.schedule_manager')
    def test_show_job(self, scheduler):
        scheduler.show.return_value = (
            True,
            {'user': u'cloudr', 'enabled': True,
             'period': '0,15,30,45 * * * *',
             'enabled': True,
             'content': 'Job content', 'name': u'job1'}
        )

        resp = self.app.get('/rest/scheduler/jobs/job1', headers={
            'Cr-Token': 'PREDEFINED_TOKEN', 'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        self.assertEqual(scheduler.show.call_args_list,
                         [call('testuser', 'job1')])

        self.assertEqual(resp_json['job'], scheduler.show.return_value[1],
                         resp.body)

    @patch('cloudrunner_server.api.v0_9.controllers.'
           'scheduler.schedule_manager')
    def test_create(self, scheduler):
        scheduler.add.return_value = (True, None)

        resp = self.app.post('/rest/scheduler/jobs',
                             "name=job1&period=* 0 * * *&content=somecontent",
                             headers={
                                 'Cr-Token': 'PREDEFINED_TOKEN',
                                 'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        self.assertEqual(scheduler.add.call_args_list,
                         [call('testuser',
                               payload='somecontent',
                               name=u'job1',
                               auth_token='PREDEFINED_TOKEN',
                               period=u'* 0 * * *')])

        self.assertRedisInc('MyOrg:scheduler.jobs')
        self.assertRedisPub('MyOrg:scheduler.jobs', 'create')

        self.assertEqual(resp_json, {"status": "ok"},
                         resp.body)

    @patch('cloudrunner_server.api.v0_9.controllers.'
           'scheduler.schedule_manager')
    def test_update(self, scheduler):
        scheduler.edit.return_value = (True, None)

        resp = self.app.patch('/rest/scheduler/jobs',
                              "name=job1&period=* 0 * * *",
                              headers={
                                  'Cr-Token': 'PREDEFINED_TOKEN',
                                  'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        self.assertEqual(scheduler.edit.call_args_list,
                         [call('testuser',
                               payload=None,
                               name=u'job1',
                               period=u'* 0 * * *')])

        self.assertRedisInc('MyOrg:scheduler.jobs')
        self.assertRedisPub('MyOrg:scheduler.jobs', 'update')

        self.assertEqual(resp_json, {"status": "ok"},
                         resp.body)

    @patch('cloudrunner_server.api.v0_9.controllers.'
           'scheduler.schedule_manager')
    def test_update_fail(self, scheduler):
        scheduler.edit.return_value = (True, None)

        resp = self.app.put('/rest/scheduler/jobs',
                            "name=job1",
                            headers={
                                'Cr-Token': 'PREDEFINED_TOKEN',
                                'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        self.assertEqual(scheduler.edit.call_args_list, [])

        self.assertRedisInc(None)
        self.assertRedisPub(None, None)

        self.assertEqual(resp_json, {"error": "Value not present: 'content'"},
                         resp.body)

    @patch('cloudrunner_server.api.v0_9.controllers.'
           'scheduler.schedule_manager')
    def test_delete_job(self, scheduler):
        scheduler.delete.return_value = (True, None)

        resp = self.app.delete('/rest/scheduler/jobs/job1',
                               headers={
                                   'Cr-Token': 'PREDEFINED_TOKEN',
                                   'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        self.assertEqual(scheduler.delete.call_args_list,
                         [call('testuser', name='job1')])

        self.assertRedisInc('MyOrg:scheduler.jobs')
        self.assertRedisPub('MyOrg:scheduler.jobs', 'delete')

        self.assertEqual(resp_json, {"status": "ok"},
                         resp.body)
