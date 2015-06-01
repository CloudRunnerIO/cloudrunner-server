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
import logging
import re
from Queue import Empty
from sys import maxint as MAX_INT
from threading import (Thread, Event)
import time

from cloudrunner.core.parser import has_params
from cloudrunner.core.exceptions import (ConnectionError, InterruptExecution,
                                         InterruptStep)
from cloudrunner_server.core.message import (M, Ready, StdOut, StdErr,
                                             FileExport, Finished, Events, Job,
                                             Term, JobTarget, SafeDictWrapper,
                                             PipeMessage, FinishedMessage,
                                             InitialMessage, SysMessage,
                                             StatusCodes)
from cloudrunner.util.string import stringify
from cloudrunner.util.string import stringify1

from cloudrunner_server.util import timestamp
LOG = logging.getLogger('ServerSession')


class JobSession(Thread):

    """
    Starts a session on the server, which is responsible for
    communication with nodes and for processing and agregating results
    """

    def __init__(self, manager, user, session_id, task_id, step_id, task,
                 remote_user_map, env_in, env_out, timeout, parent,
                 stop_event=None, **kwargs):
        super(JobSession, self).__init__()
        self.session_id = str(session_id)
        self.user = user
        self.step_id = step_id
        self.task_id = task_id
        self.task = SafeDictWrapper(task)
        self.remote_user_map = remote_user_map
        self.stop_reason = 'term'
        self.session_event = stop_event or Event()
        self.task_name = str(kwargs.get('caller', ''))
        self.manager = manager
        self.timeout = (self.task.timeout
                        or kwargs.get('timeout')
                        or self.manager.wait_timeout)
        if self.timeout:
            self.timeout = int(self.timeout)
        self.env_in = env_in
        self.env_out = env_out
        self.global_timeout = self.timeout
        self.parent = parent
        self.env = {}
        self.node_map = kwargs.pop("node_map", {})
        self.restore = False
        self.user_org = (self.user, self.remote_user_map['org'])
        self.attachments = []
        self.start_at = kwargs.get('start_at', 0)
        self.request = dict(env=self.env, script=self.task.body,
                            remote_user_map=self.remote_user_map)
        self.file_exports = {}
        self.disabled_nodes = [n.lower() for n in
                               kwargs.get("disabled_nodes", [])]

        self.kwargs = kwargs

    def serialize(self):
        ser = dict(task=self.task, session_id=self.session_id,
                   timeout=self.timeout, parent=self.parent,
                   task_name=self.task_name, user=self.user,
                   remote_user_map=self.remote_user_map,
                   node_map=self.node_map, start_at=self.start_at,
                   step_id=self.step_id, disabled_nodes=self.disabled_nodes,
                   kwargs=self.kwargs)
        return ser

    def _reply(self, message):
        seq = timestamp()
        message.seq_no = seq
        self.job_done.send(message._)

    def run(self):
        try:
            self._run()
        except Exception, ex:
            LOG.exception(ex)
            self.env_out.put((self.env, None))

    def _execute(self):
        message = InitialMessage(session_id=self.session_id,
                                 ts=self._create_ts(),
                                 org=self.user_org[1],
                                 user=self.user_org[0])
        self._reply(message)

        try:
            env, self.file_exports = self.env_in.get(True, self.global_timeout)
        except Empty:
            _msg = "Timeout waiting for previous task to finish"
            message = SysMessage(session_id=self.task_id,
                                 ts=self._create_ts(),
                                 org=self.user_org[1],
                                 user=self.user_org[0],
                                 stdout=_msg)
            self._reply(message)
            LOG.warn(_msg)
            return

        if self.session_event.is_set():
            return

        self.env = env
        if not env:
            env = {}
        elif not isinstance(env, dict):
            LOG.warn("Invalid ENV passed: %s" % env)
            env = {}

        if self.timeout == -1:
            # Persistent job
            LOG.info("Persistent session [%s] started" % self.session_id)
            self.timeout = MAX_INT
        else:
            LOG.info("Session [%s] started(timeout: %s)" % (
                self.session_id,
                self.timeout))

        if 'attachments' in self.kwargs:
            try:
                # process runtime includes
                self.attachments.append(self.kwargs['attachments'])
            except Exception, ex:
                LOG.exception(ex)
        if self.file_exports:
            self.attachments.append(self.file_exports)

        ts = self._create_ts()
        message = SysMessage(session_id=self.task_id,
                             ts=ts,
                             org=self.user_org[1],
                             user=self.user_org[0],
                             stdout="[%s] Starting task #%s" %
                             (datetime.now().strftime('%c'), self.step_id + 1))
        self._reply(message)

        # Clean up
        self.kwargs.pop('user_org', None)
        self.kwargs.pop('section', None)
        self.kwargs.pop('tgt_args', None)

        try:
            if self.task.pre_conditions:
                for condition in self.task.pre_conditions:
                    try:
                        pass
                    except InterruptStep:
                        LOG.warn("BEFORE: Step execution interrupted by %s" %
                                 condition)
                        raise
                    except InterruptExecution:
                        LOG.warn(
                            "BEFORE: Session execution interrupted by %s" %
                            condition)
                        raise

            self.request['env'].update(env)

            #
            # Exec section
            #
            self.run_script(
                self.task.targets)

        except Exception, ex:
            LOG.exception(ex)

    def _run(self):
        self.manager.register_session(self.session_id)
        self.job_done = self.manager.backend.publish_queue('logger')

        if not self.restore:
            self._execute()

        result = {}
        env = self.env or {}
        msg_ret = []

        try:
            for _reply in self.read():
                if _reply[0] == 'PIPE':
                    # reply: 'PIPE', self.session_id, ts, run_as, node_id,
                    # stdout, stderr
                    names = ("session_id", "ts", "run_as", "node",
                             "stdout", "stderr")
                    message = PipeMessage(user=self.user,
                                          org=self.remote_user_map['org'],
                                          **dict(zip(names, _reply[1:])))
                    self._reply(message)
                else:
                    self.session_id, msg_ret, file_exports = _reply
                    break

            new_env = {}
            # [{'node': 'yoga', 'remote_user': '@', 'env': {},
            # 'stderr': '', 'stdout': '', 'ret_code': 0}]

            for _ret in msg_ret:
                _env = _ret.pop('env', {})
                _stdout = _ret.get('stdout', '')
                _stderr = _ret.pop('stderr', '')
                _node = _ret.pop('node')

                if _stdout or _stderr:
                    ts = self._create_ts()
                    message = PipeMessage(user=self.user,
                                          org=self.remote_user_map['org'],
                                          ts=ts,
                                          session_id=self.session_id,
                                          run_as=_ret.get('run_as'),
                                          node=_node,
                                          stdout=_stdout,
                                          stderr=_stderr)
                    self._reply(message)

                result[_node] = _ret
                for k, v in _env.items():
                    if k in new_env:
                        if not isinstance(new_env[k], list):
                            new_env[k] = [new_env[k]]
                        if isinstance(v, list):
                            new_env[k].extend(list(stringify(*v)))
                        else:
                            new_env[k].append(stringify1(v))
                    else:
                        new_env[k] = v

            env.update(new_env)
            if self.task.post_conditions:
                for condition in self.task.post_conditions:
                    try:
                        pass
                    except InterruptStep:
                        LOG.warn("BEFORE: Step execution interrupted by %s" %
                                 condition)
                        raise
                    except InterruptExecution:
                        LOG.warn(
                            "BEFORE: Session execution interrupted by %s" %
                            condition)
                        raise
        except Exception, ex:
            LOG.exception(ex)
        finally:
            time.sleep(.5)
            ts = self._create_ts()
            message = FinishedMessage(ts=ts,
                                      session_id=self.session_id,
                                      user=self.user,
                                      org=self.remote_user_map['org'],
                                      result=result,
                                      env=env)
            self._reply(message)
            self.env_out.put((env, self.file_exports))

        # Wait for all other threads to finish consuming session data
        time.sleep(.5)
        self.job_done.close()

    def run_script(self, targets):
        """
        Send request to nodes
        Arguments:

        targets     --  Target nodes, described by Id or Selector

        """
        targets = [t['name'] if isinstance(t, dict) else t for t in targets]
        env = self.request['env']
        for i, t in enumerate(targets):
            params = has_params(t)
            if params:
                for sel_param in params:
                    sel, param = sel_param
                    param_name = param.replace('$', '')
                    if param_name in env:
                        param_val = env[param_name]
                        if isinstance(param_val, list):
                            repl_params = ' '.join(
                                ['%s%s' % (sel, val) for val in param_val])
                        else:
                            repl_params = sel + param_val
                        targets[i] = t.replace(sel + param, repl_params)

        remote_user_map = self.request.pop('remote_user_map')

        target = JobTarget(self.session_id, str(" ".join(targets)))
        target.hdr.org = remote_user_map['org']
        self.start_at = timestamp()
        self.manager.publisher.send(target._)

    def read(self):
        job_event = Event()
        user_map = UserMap(self.remote_user_map['roles'], self.user)
        node_map = self.node_map

        job_reply = self.manager.backend.publish_queue('out_messages')
        job_queue = self.manager.backend.consume_queue('in_messages',
                                                       ident=self.session_id)
        user_input_queue = self.manager.backend.consume_queue(
            'user_input',
            ident=self.session_id)

        poller = self.manager.backend.create_poller(job_queue,
                                                    user_input_queue)
        discovery_period = time.time() + self.manager.discovery_timeout
        total_wait = time.time() + (self.timeout or self.manager.wait_timeout)

        try:
            while not self.session_event.is_set() and not job_event.is_set():
                ready = poller.poll()

                if user_input_queue in ready:
                    frames = user_input_queue.recv()

                    # input from user -> node
                    """
                    input_req = JobInput.build(*frames)
                    if not input_req:
                        LOG.warn("Invalid request %s" % frames)
                        continue

                    for node, data in node_map.items():
                        if input_req.cmd == 'INPUT' and \
                            (input_req.targets == '*' or
                                node in input_req.targets):
                            job_reply.send(
                                R(data['router_id'],
                                  Input.build(self.session_id,
                                              input_req.cmd,
                                              input_req.data)._)._)
                    """
                    continue

                frames = None
                if job_queue in ready:
                    frames = job_queue.recv()

                if not frames:
                    if time.time() > discovery_period:
                        # Discovery period ended, check for results
                        if not any([n['status'] in StatusCodes.pending()
                                    for n in node_map.values()]):
                            break

                    if time.time() > total_wait:
                        _msg = 'Timeout waiting for response from nodes'
                        LOG.warn(_msg)
                        message = SysMessage(session_id=self.task_id,
                                             ts=self._create_ts(),
                                             org=self.user_org[1],
                                             user=self.user_org[0],
                                             stdout=_msg)
                        self._reply(message)

                        for node in node_map.values():
                            if node['status'] != StatusCodes.FINISHED:
                                node['data']['stderr'] = \
                                    node['data'].setdefault('stderr',
                                                            '') + \
                                    'Timeout waiting response from node'
                        LOG.debug(node_map)
                        job_event.set()
                        break

                    continue

                job_rep = M.build(frames[0])
                if not job_rep:
                    LOG.error("Invalid reply from node: %s" % frames)
                    continue

                # Assert we have rep from the same organization
                if job_rep.hdr.org != self.remote_user_map['org']:
                    continue

                state = node_map.setdefault(
                    job_rep.hdr.peer, dict(status=StatusCodes.STARTED,
                                           data={},
                                           stdout='',
                                           stderr=''))

                ts = self._create_ts()
                node_map[job_rep.hdr.peer]['router_id'] = job_rep.hdr.ident
                if isinstance(job_rep, Ready):
                    remote_user = user_map.select(job_rep.hdr.peer)
                    if not remote_user:
                        LOG.info("Node %s not allowed for user %s" % (
                            job_rep.hdr.peer,
                            self.user))
                        node_map.pop(job_rep.hdr.peer)
                        continue
                    if job_rep.hdr.peer.lower() in self.disabled_nodes:
                        LOG.info("Node %s is disabled" % job_rep.hdr.peer)
                        node_map.pop(job_rep.hdr.peer)
                        continue
                    # Send task to attached node
                    node_map[job_rep.hdr.peer]['remote_user'] = remote_user
                    _msg = "Sending job to %s" % job_rep.hdr.peer
                    LOG.info(_msg)
                    message = SysMessage(session_id=self.task_id,
                                         ts=self._create_ts(),
                                         org=self.user_org[1],
                                         user=self.user_org[0],
                                         stdout=_msg)

                    job_msg = Job(self.session_id, remote_user, self.request)
                    job_msg.hdr.ident = job_rep.hdr.ident
                    job_msg.hdr.dest = self.session_id
                    job_reply.send(job_msg._)
                    continue

                state['status'] = job_rep.control
                if isinstance(job_rep, Finished):
                    state['data']['elapsed'] = int(timestamp() - self.start_at)
                    state['data']['ret_code'] = job_rep.result['ret_code']
                    state['data']['env'] = job_rep.result['env']
                    if job_rep.result['stdout'] or job_rep.result['stderr']:
                        yield ('PIPE', self.session_id, ts,
                               job_rep.run_as,
                               job_rep.hdr.peer,
                               job_rep.result['stdout'],
                               job_rep.result['stderr'])
                elif isinstance(job_rep, StdOut):
                    yield ('PIPE', self.session_id, ts,
                           job_rep.run_as,
                           job_rep.hdr.peer,
                           job_rep.output, '')
                elif isinstance(job_rep, StdErr):
                    yield ('PIPE', self.session_id, ts,
                           job_rep.run_as,
                           job_rep.hdr.peer,
                           '', job_rep.output)
                elif isinstance(job_rep, FileExport):
                    file_name = '%s_%s' % (job_rep.hdr.peer, job_rep.file_name)
                    self.file_exports[file_name] = job_rep.content
                elif isinstance(job_rep, Events):
                    LOG.info("Polling events for %s" % self.session_id)
                # else:
                #    job_reply.send(job_rep.ident, job_rep.peer,
                #    self.session_id,'UNKNOWN')

                LOG.debug('Resp[%s]:: [%s][%s]' % (self.session_id,
                                                   job_rep.hdr.peer,
                                                   job_rep.control))
        except ConnectionError:
            # Transport died
            self.session_event.set()
        except Exception, ex:
            LOG.exception(ex)
        finally:
            # LOG.warning(node_map)
            if self.session_event.is_set() or job_event.is_set():
                # Forced stop ?
                # ToDo: check arg flag to keep task running
                for name, node in node_map.items():
                    try:
                        job_msg = Term(self.session_id, self.stop_reason)
                        job_msg.hdr.ident = node['router_id']
                        job_msg.hdr.dest = self.session_id
                        job_reply.send(job_msg._)
                    except:
                        continue

                # Wait for jobs to finalize
                job_event.wait(1)
                for name, node in node_map.items():
                    if node['status'] != StatusCodes.FINISHED:
                        node['status'] = StatusCodes.FINISHED
                        node['stderr'] = \
                            node['data'].setdefault('stderr', '') + \
                            '\nJob execution stopped: [%s]' % self.stop_reason

                        ts = self._create_ts()
                        yield ('PIPE', self.session_id, ts, '', name,
                               node['stdout'], node['stderr'])

            job_event.set()

        user_input_queue.close()
        job_queue.close()
        job_reply.close()
        self.manager.delete_session(self.session_id)

        yield (self.session_id,
               [dict(node=k,
                     remote_user=n['remote_user'],
                     env=n['data'].get('env', {}),
                     stdout=n['data'].get('stdout', ''),
                     stderr=n['data'].get('stderr', ''),
                     elapsed=n['data'].get('elapsed', 0),
                     ret_code=n['data'].get('ret_code', -255))
                for k, n in node_map.items()],
               self.file_exports)

    def _create_ts(self):
        ts = timestamp()
        millis = round(time.time() % 1, 3)
        ts += millis
        return ts


class UserMap(object):

    def __init__(self, role_map, user):
        self.rules = {}
        self.default = None
        self.user = user
        for k, v in role_map.items():
            if k == '*':
                self.default = v
            else:
                try:
                    self.rules[v] = re.compile(k)
                except:
                    pass

    def select(self, node):
        for role, rule in self.rules.items():
            if rule.match(node):
                LOG.info("Rule %s applied for user %s" % (node, self.user))
                return role

        if self.default:
            LOG.info("Default rule for %s applied for user %s" % (node,
                                                                  self.user))
            return self.default

        return None
