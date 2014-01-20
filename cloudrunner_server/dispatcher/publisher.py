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

import argparse
import json
import logging
import time
import threading
import zmq

from cloudrunner.core.message import JobRep
from cloudrunner.core.message import StatusCodes
from cloudrunner_server.dispatcher import Promise
from cloudrunner_server.dispatcher.session import ServerSession

LOG = logging.getLogger('Publisher')


class Publisher(object):

    def __init__(self, config, ctx, transport, job_done_uri, plugins_ctx=None):
        self.config = config
        self.transport = transport
        self.discovery_timeout = int(self.config.discovery_timeout or 2)
        self.wait_timeout = int(self.config.wait_timeout or 300)
        self.sessions = {}
        self.subscriptions = {}
        self.plugins_ctx = plugins_ctx

        self.opt_parser = argparse.ArgumentParser(add_help=False)
        self.opt_parser.add_argument('-t', '--timeout')

        self.context = ctx
        self.job_done_uri = job_done_uri

    def start(self):
        self.transport.start()

    def _reply(self, session_id, ret_type, data):
        for sub in self.subscriptions.get(session_id, []):
            self.job_done.send_multipart(
                [sub.peer, ret_type, json.dumps(data)])

    def prepare_session(self, user, session_id, payload,
                        remote_user_map, **kwargs):
        promise = Promise(session_id)
        promise.owner = user
        sess_thread = ServerSession(self, user, session_id, payload,
                                    remote_user_map, threading.Event(),
                                    **kwargs)
        promise.resolve = lambda: sess_thread.start()
        self.subscriptions[session_id] = [promise]
        self.sessions[session_id] = sess_thread
        return promise

    def notify(self, session_id, job_id, payload, targets,
               remote_user_map, **kwargs):
        self.transport.publish(
            remote_user_map.org, 'NOTIFY', session_id, job_id,
            targets, str(payload))

    def terminate(self, session_id, payload, remote_user_map, **kwargs):
        for sess_id in self.sessions.keys():
            if session_id == session_id:
                session = self.sessions[sess_id]
                session.reason = payload
                session.session_event.set()
                del self.sessions[sess_id]
                break

        self.transport.publish(
            remote_user_map.org, 'NOTIFY', session_id, job_id,
            targets, str(payload))

    def stop(self):
        LOG.info("Stopping Publisher")
        for session in self.sessions.values():
            session.session_event.set()
        self.transport.destroy_jobs()
        for session in self.sessions.values():
            session.join(.2)
