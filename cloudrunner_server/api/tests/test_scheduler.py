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
from mock import Mock

from cloudrunner_server.api.tests import base

ctx_mock = Mock()
sock_mock = Mock()
ctx_mock.socket.return_value = sock_mock


class TestScheduler(base.BaseRESTTestCase):

    def test_list_jobs(self):
        cr_data = {'jobs': [
            {
                'name': 'Job 1',
                'created_at': '2015-05-23 00:00:00',
                'enabled': True,
                'private': False,
                'params': None,
                'automation': 'My deployment',
                'owner': 'testuser',
                'exec_period': '* * * * *'}],
            'quota': {'allowed': 10}}

        resp = self.app.get('/rest/scheduler/jobs', headers={
            'Cr-Token': 'PREDEFINED_TOKEN', 'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)
        self.assertEqual(resp_json, cr_data)

    def test_list_job(self):
        cr_data = {'job': {
            'name': 'Job 1',
            'created_at': '2015-05-23 00:00:00',
            'enabled': True,
            'private': False,
            'params': None,
            'automation': 'My deployment',
            'owner': 'testuser',
            'exec_period': '* * * * *'}
        }

        resp = self.app.get('/rest/scheduler/jobs/Job 1', headers={
            'Cr-Token': 'PREDEFINED_TOKEN', 'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        self.maxDiff = None
        resp_json = json.loads(resp.body)
        self.assertEqual(resp_json, cr_data)

    def test_create_jobs(self):
        cr_data = {'jobs': [
            {
                'name': 'Job 1',
                'enabled': True,
                'private': False,
                'params': None,
                'automation': 'My deployment',
                'owner': 'testuser',
                'exec_period': '* * * * *'},
            {
                'name': 'Job 11',
                'enabled': True,
                'private': False,
                'params': {},
                'automation': 'My deployment',
                'owner': 'testuser',
                'exec_period': '0 0 * * *'}],
            'quota': {'allowed': 10}}

        resp = self.app.post(
            '/rest/scheduler/jobs',
            'name=Job 11&automation=My deployment&private=0&period=0 0 * * *',
            headers={
                'Cr-Token': 'PREDEFINED_TOKEN', 'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)
        self.assertEqual(resp_json, {'success': {'status': 'ok'}})

        resp = self.app.get('/rest/scheduler/jobs', headers={
            'Cr-Token': 'PREDEFINED_TOKEN', 'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)
        resp_json['jobs'][0].pop('created_at')
        resp_json['jobs'][1].pop('created_at')
        self.maxDiff = None
        self.assertEqual(resp_json, cr_data)

    def test_delete_job(self):

        resp = self.app.delete('/rest/scheduler/jobs/Job 1',
                               headers={
                                   'Cr-Token': 'PREDEFINED_TOKEN',
                                   'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = json.loads(resp.body)

        self.assertEqual(resp_json, {"success": {"status": "ok"}})
