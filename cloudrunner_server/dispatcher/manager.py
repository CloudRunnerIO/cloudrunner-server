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
import logging
from os import path
from Queue import Queue
import uuid

from cloudrunner import LIB_DIR
from cloudrunner.core.message import SafeDictWrapper
from cloudrunner_server.dispatcher import TaskQueue
from cloudrunner_server.dispatcher.session import JobSession

LOG = logging.getLogger('Publisher')


class SessionManager(object):

    def __init__(self, config, backend):
        self.config = config
        self.backend = backend
        self.discovery_timeout = int(self.config.discovery_timeout or 2)
        self.wait_timeout = int(self.config.wait_timeout or 300)
        self.sessions = {}
        self.subscriptions = []

        self.publisher = self.backend.create_fanout('publisher')

        # Restore jobs
        self.cache = self.config.session_cache or path.join(
            LIB_DIR, "session.cache")
        if path.exists(self.cache):
            cached = open(self.cache).read().strip()
            if cached:
                try:
                    sessions = json.loads(cached, encoding='latin-1')
                    self.resume_sessions(*sessions)

                except Exception, ex:
                    LOG.exception(ex)

    def prepare_session(self, user, tasks,
                        remote_user_map, **kwargs):
        queue = TaskQueue()
        queue.owner = user
        timeout = 0
        env_in = Queue()
        env_in.put((kwargs.get('env', {}), kwargs.get('attachments')))
        env_out = Queue()
        prev = None
        for task in tasks:
            session_id = uuid.uuid4().hex
            LOG.info("Enqueue new session %s" % session_id)
            sess_thread = JobSession(self, user, session_id, task,
                                     remote_user_map, env_in, env_out,
                                     timeout, prev, **kwargs)
            timeout += sess_thread.timeout + 2
            env_in = env_out
            env_out = Queue()
            queue.push(sess_thread)
            self.sessions[session_id] = sess_thread
            prev = session_id
        self.subscriptions.append(queue)
        return queue

    def resume_sessions(self, *sessions):
        queue = TaskQueue()
        timeout = 0
        sessions = sorted(sessions, key=lambda s: bool(s.get('parent')))
        for session in sessions:
            try:
                s = SafeDictWrapper(session)
                session_id = s['session_id']
                LOG.info("Resume session %s" % session_id)

                env_in = None
                restore = True
                if s.parent:
                    parent = any([sess for sess in sessions
                                  if sess.session_id == s.parent])
                    if parent:
                        parent_thread = queue.find(s.parent)
                        if parent_thread:
                            env_in = parent_thread.env_out

                env_out = Queue()
                sess_thread = JobSession(self, s.user, session_id, s.task,
                                         s.remote_user_map, env_in,
                                         env_out, s.timeout, s.parent,
                                         node_map=s.node_map,
                                         **s.kwargs)
                sess_thread.restore = restore
                timeout += sess_thread.timeout + 2
                queue.push(sess_thread)
                self.sessions[session_id] = sess_thread
            except Exception, ex:
                LOG.exception(ex)
        self.subscriptions.append(queue)
        queue.process()

    def register_session(self, session_id):
        self.backend.register_session(session_id)

    def delete_session(self, session_id):
        self.backend.unregister_session(session_id)
        try:
            del self.subscriptions[self.session_id]
        except:
            pass
        try:
            del self.sessions[session_id]
        except:
            pass

    def notify(self, session_id, job_id, payload, targets,
               remote_user_map, **kwargs):
        self.publisher.send(
            remote_user_map.org, 'NOTIFY', session_id, job_id,
            targets, str(payload))

    def stop(self):
        LOG.info("Stopping Publisher")
        open(self.cache, 'w').write(json.dumps(
            [sess.serialize() for sess in self.sessions.values()],
            ensure_ascii=False))
        for session in self.sessions.values():
            session.session_event.set()
        # self.transport.destroy_jobs()
        for session in self.sessions.values():
            if session.is_alive():
                session.session_event.set()
                session.env_in.put({})
                session.join(.2)

        LOG.info("Stopped Publisher")
