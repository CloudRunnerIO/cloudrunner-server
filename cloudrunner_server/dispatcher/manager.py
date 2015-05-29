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
from threading import Thread, Event
import time
from Queue import Queue, Empty
import uuid

from sqlalchemy import create_engine, event
from sqlalchemy.orm import scoped_session, sessionmaker

from cloudrunner import LIB_DIR
from cloudrunner_server.api.model import (CloudProfile, NodeGroup, User,
                                          TaskGroup, Resource, metadata)
from cloudrunner_server.core.message import (SafeDictWrapper, InitialMessage,
                                             EndMessage, SysMessage)
from cloudrunner_server.dispatcher import TaskQueue
from cloudrunner_server.dispatcher.session import JobSession
from cloudrunner_server.plugins.clouds.base import BaseCloudProvider
from cloudrunner_server.util import timestamp
from cloudrunner_server.util.db import checkout_listener

LOG = logging.getLogger('Publisher')


class SessionManager(object):

    def __init__(self, config, backend):
        self.config = config
        self.db_path = config.db
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

    def set_context_from_config(self, recreate=None, **configuration):
        session = scoped_session(sessionmaker())
        engine = create_engine(self.db_path, **configuration)
        if 'mysql+pymysql://' in self.db_path:
            event.listen(engine, 'checkout', checkout_listener)
        session.bind = engine
        metadata.bind = session.bind
        if recreate:
            # For tests: re-create tables
            metadata.create_all(engine)
        self.db = session

    def _expand_target(self, targets):
        possible_groups = [t for t in targets if not isinstance(t, dict)
                           and "=" not in t]
        expanded_nodes = []
        if possible_groups:
            groups = self.db.query(NodeGroup).filter(
                NodeGroup.name.in_(targets)).all()
            for g in groups:
                for n in g.nodes:
                    expanded_nodes.append(n.name)

        return targets + expanded_nodes

    def prepare_session(self, user, task_id, tasks,
                        remote_user_map, **kwargs):
        queue = TaskQueue()
        queue.owner = user
        timeout = 0
        env_in = Queue()
        start_args = (kwargs.get('env', {}), kwargs.get('attachments'))
        # env_in.put()
        env_out = Queue()
        global_job_event = Event()
        for task in tasks:
            task['targets'] = self._expand_target(task['targets'])

        prepare_thread = PrepareThread(self, task_id, user, task_id,
                                       tasks, remote_user_map['org'],
                                       env_in, start_args,
                                       global_job_event)
        queue.prepare(prepare_thread)

        prev = None
        for step_id, task in enumerate(tasks):

            session_id = uuid.uuid4().hex
            LOG.info("Enqueue new session %s" % session_id)
            sess_thread = JobSession(self, user, session_id, task_id, step_id,
                                     task, remote_user_map, env_in, env_out,
                                     timeout, prev,
                                     stop_event=global_job_event, **kwargs)
            timeout += sess_thread.timeout + 2
            env_in = env_out
            env_out = Queue()
            queue.push(sess_thread)
            self.sessions[session_id] = sess_thread
            prev = session_id
        if queue.tasks:
            end_thread = EndThread(self, session_id, task_id, user,
                                   remote_user_map['org'],
                                   queue.tasks[-1].env_out,
                                   timeout)
            queue.callback(end_thread)
        self.subscriptions.append(queue)
        return queue

    def resume_sessions(self, *sessions):
        queue = TaskQueue()
        timeout = 0
        sessions = sorted(sessions, key=lambda s: bool(s.get('parent')))
        env_out = Queue()
        for session in sessions:
            try:
                s = SafeDictWrapper(session)
                session_id = s['session_id']
                LOG.info("Resume session %s" % session_id)

                env_in = None
                restore = True
                if s.parent:
                    parent = any([sess for sess in sessions
                                  if sess['session_id'] == s.parent])
                    if parent:
                        parent_thread = queue.find(s.parent)
                        if parent_thread:
                            env_in = parent_thread[0].env_out

                env_out = Queue()
                sess_thread = JobSession(self, s.user, s.task_id, session_id,
                                         s.step_id, s.task, s.remote_user_map,
                                         env_in, env_out, s.timeout, s.parent,
                                         node_map=s.node_map,
                                         **s.kwargs)
                sess_thread.restore = restore
                queue.push(sess_thread)
                self.sessions[session_id] = sess_thread
            except Exception, ex:
                LOG.exception(ex)
        if queue.tasks:
            end_thread = EndThread(self, session_id, s.task_id, s.user,
                                   s.remote_user_map['org'],
                                   queue.tasks[-1].env_out,
                                   timeout)
            queue.callback(end_thread)
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


class PrepareThread(Thread):

    def __init__(self, manager, session_id, user, task_id, tasks,
                 org, out_queue, start_args, job_event):
        super(PrepareThread, self).__init__()
        self.session_id = str(session_id)
        self.user = user
        self.task_id = task_id
        self.tasks = tasks
        self.org = org
        self.out_queue = out_queue
        self.start_args = start_args
        self.manager = manager
        self.job_event = job_event
        self.job_done = self.manager.backend.publish_queue('logger')

    def log(self, stdout=None, stderr=None):
        message = SysMessage(session_id=self.session_id, ts=timestamp(),
                             org=self.org, user=self.user,
                             stdout=stdout, stderr=stderr)
        self.job_done.send(message._)

    def run(self):
        waiter = Event()
        targets = []
        self.node_connected = self.manager.backend.subscribe_fanout(
            'admin_fwd', sub_patterns=[self.org])

        message = InitialMessage(session_id=self.session_id,
                                 ts=timestamp(),
                                 org=self.org,
                                 user=self.user)
        self.job_done.send(message._)

        wait_for_machines = []
        for task in self.tasks:
            for target in task['targets']:
                if isinstance(target, dict):
                    if target['name'] in targets:
                        continue
                    targets.append(target['name'])

                    # Provider value
                    server_name = target.pop('name')
                    self.manager.user = self.manager.db.query(User).filter(
                        User.username == self.user).first()
                    profile = CloudProfile.my(self.manager).filter(
                        CloudProfile.name == target['provider']).first()

                    if not profile:
                        msg = ("Cloud profile: '%s' not found!" %
                               target['provider'])
                        self.log(stderr=msg)
                        raise ValueError(msg)
                    if profile.shared:
                        profile = profile.shared
                    task_group = self.manager.db.query(TaskGroup).filter(
                        TaskGroup.id == self.task_id).first()
                    if not task_group:
                        msg = ("Invalid task group: %s" %
                               self.task_id)
                        self.log(stderr=msg)
                        raise ValueError(msg)

                    deployment = task_group.deployment
                    if not deployment:
                        return
                    provider = BaseCloudProvider.find(profile.type)
                    if not provider:
                        msg = ("Cloud profile type '%s' not supported!" %
                               profile.type)
                        self.log(stderr=msg)
                        raise ValueError(msg)
                    status, machine_ids, meta = provider(
                        profile).create_machine(server_name, **target)
                    for m_id in machine_ids:
                        res = Resource(server_name=server_name, server_id=m_id,
                                       deployment=deployment, profile=profile,
                                       meta=json.dumps(meta))
                        self.manager.db.add(res)
                    self.manager.db.commit()
                    wait_for_machines.append(server_name)
                    # Return arg to dict
                    target['name'] = server_name
                    targets.append(server_name)
                else:
                    targets.append(target)

        if wait_for_machines:
            try:
                max_timeout = time.time() + 600  # 10 minutes
                while not waiter.is_set():
                    ret = self.node_connected.recv(timeout=1)
                    if ret:
                        msg = "Node %s has just appeared online" % ret[0]
                        self.log(stdout=msg)
                        LOG.warn(msg)
                        if ret[1] in wait_for_machines:
                            wait_for_machines.remove(ret[1])
                        if not any(wait_for_machines):
                            waiter.set()
                    else:
                        if time.time() > max_timeout:
                            msg = ("Timeout waiting to create nodes")
                            self.log(stderr=msg)
                            LOG.error(msg)
                            waiter.set()
                            # Set global event to prevent task execution
                            self.job_event.set()

            except Exception, ex:
                LOG.exception(ex)
                self.log(stderr=ex.message)

        self.out_queue.put(self.start_args)
        self.node_connected.close()
        self.job_done.close()


class EndThread(Thread):

    def __init__(self, manager, session_id, task_id, user, org, event,
                 timeout):
        super(EndThread, self).__init__()
        self.session_id = str(session_id)
        self.task_id = str(task_id)
        self.org = org
        self.user = user
        self.event = event
        self.timeout = timeout
        self.job_done = manager.backend.publish_queue('logger')

    def log(self, stdout=None, stderr=None):
        message = SysMessage(session_id=self.task_id, ts=timestamp(),
                             org=self.org, user=self.user,
                             stdout=stdout, stderr=stderr)
        self.job_done.send(message._)

    def run(self):
        try:
            self.event.get(True, self.timeout)
        except Empty:
            pass
        self.log(stdout="Finished processing tasks")
        message = EndMessage(session_id=self.session_id, org=self.org)
        self.job_done.send(message._)
        self.job_done.close()
