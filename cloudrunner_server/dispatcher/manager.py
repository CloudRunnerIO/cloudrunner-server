#!/usr/bin/python
# -*- coding: utf-8 -*-
# vim: tabstop=4 shiftwidth=4 softtabstop=4

# /*******************************************************
#  * Copyright (C) 2013-2014 CloudRunner.io <info@cloudrunner.io>
#  *
#  * Proprietary and confidential
#  * This file is part of CloudRunner Server.
#  *
#  * CloudRunner Server can not be copied and/or distributed without the express
#  * permission of CloudRunner.io
#  *******************************************************/

import argparse
import json
import logging
import time
import threading
from threading import Thread
from multiprocessing import Process

from cloudrunner.core.message import JobRep
from cloudrunner.core.message import StatusCodes
from cloudrunner_server.dispatcher import Promise
from cloudrunner_server.dispatcher.session import JobSession

LOG = logging.getLogger('Publisher')


class SessionManager(object):

    def __init__(self, config, backend):
        self.config = config
        self.backend = backend
        self.discovery_timeout = int(self.config.discovery_timeout or 2)
        self.wait_timeout = int(self.config.wait_timeout or 300)
        self.sessions = {}
        self.subscriptions = {}

        self.opt_parser = argparse.ArgumentParser(add_help=False)
        self.opt_parser.add_argument('-t', '--timeout')

        self.publisher = self.backend.create_fanout('publisher')

    def prepare_session(self, user, session_id, payload,
                        remote_user_map, plugin_ctx, **kwargs):
        promise = Promise(session_id)
        promise.owner = user
        sess_thread = JobSession(self, user, session_id, payload,
                                 remote_user_map, threading.Event(),
                                 plugin_ctx, **kwargs)
        promise.resolve = lambda: sess_thread.start()
        self.subscriptions[session_id] = [promise]
        self.sessions[session_id] = sess_thread
        return promise

    def notify(self, session_id, job_id, payload, targets,
               remote_user_map, **kwargs):
        self.publisher.send(
            remote_user_map.org, 'NOTIFY', session_id, job_id,
            targets, str(payload))

    def stop(self):
        LOG.info("Stopping Publisher")
        for session in self.sessions.values():
            session.session_event.set()
        # self.transport.destroy_jobs()
        for session in self.sessions.values():
            session.join(.2)
