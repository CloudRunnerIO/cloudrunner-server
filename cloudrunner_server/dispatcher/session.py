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

import logging
import re
from sys import maxint as MAX_INT
from threading import (Thread, Event)
import time
import uuid

from cloudrunner.core import parser
from cloudrunner.core.exceptions import (ConnectionError,
                                         InterruptStep,
                                         InterruptExecution)
from cloudrunner.core.message import (M, Ready, StdOut, StdErr,
                                      Finished, Events, Job, Term, JobTarget)
from cloudrunner.core.message import (InitialMessage,
                                      PipeMessage,
                                      FinishedMessage)
from cloudrunner.core.message import StatusCodes
from cloudrunner.util.string import stringify
from cloudrunner.util.string import stringify1

LOG = logging.getLogger('ServerSession')


class JobSession(Thread):

    """
    Starts a session on the server, which is responsible for
    communication with nodes and for processing and agregating results
    """

    def __init__(self, manager, user, session_id, payload, remote_user_map,
                 stop_event, plugin_ctx, **kwargs):
        super(JobSession, self).__init__()
        self.session_id = session_id
        self.user = user
        self.payload = payload
        self.remote_user_map = remote_user_map
        self.kwargs = kwargs
        self.stop_reason = 'term'
        self.session_event = stop_event
        self.task_name = str(kwargs.get('caller', ''))
        self.timeout = kwargs.get('timeout')
        self.manager = manager
        self.plugin_context = plugin_ctx
        self.seq = 1

    def _reply(self, message):
        message.seq_no = self.seq
        self.seq += 1
        self.job_done.send(message._)
        """
        for sub in self.manager.subscriptions.get(message.session_id, []):
            try:
                self.job_done.send(*message.pack(sub.proxy, sub.peer))
            except zmq.ZMQError as zerr:
                if self.manager.context.closed or zerr.errno == zmq.ETERM \
                        or zerr.errno == zmq.ENOTSOCK:
                    break
            except ConnectionError:
                break
        """

    def parse_script(self, env):
        self.sections = []

        _sections = parser.split_sections(self.payload)

        for i in range(1, len(_sections), 2):
            targets = None
            tgt_args = None
            tgt_args_string = None

            target_str = _sections[i]
            _section = _sections[i + 1]

            (targets, req_args) = parser.parse_selectors(target_str)

            _args = [a for a in req_args.split() if a.strip()]
            if self.plugin_context.args_plugins:
                (valid, invalid) = self.plugin_context.args_plugins.\
                    parse_known_args(_args)
                tgt_args = valid
                tgt_args_string = list(set(_args) - set(invalid))

            # Data section
            section = Section()
            section.data = _section
            section.targets = targets
            section.args = tgt_args
            section.args_string = tgt_args_string

            self.sections.append(section)

        if not _sections:
            LOG.warn("Request without executable sections")

    def run(self):
        try:
            self._run()
        except Exception, ex:
            LOG.exception(ex)

    def _run(self):
        env = self.kwargs.pop('env', {})
        if not isinstance(env, dict):
            LOG.warn("Invalid ENV passed: %s" % env)
            env = {}
        self.parse_script(env)

        self.job_done = self.manager.backend.publish_queue('logger')

        ret = []
        timeout = None

        timeout = self.kwargs.get('timeout', None)
        if timeout:
            try:
                timeout = int(timeout)
            except:
                timeout = None

        common_opts = parser.parse_common_opts(self.payload)
        if common_opts:
            args, __ = self.manager.opt_parser.parse_known_args(
                common_opts[1].split())
            if not timeout and args.timeout:
                # read from opts
                try:
                    timeout = int(args.timeout)
                except:
                    pass

        if timeout == -1:
            # Persistent job
            LOG.info("Persistent Session started(%s)" % self.session_id)
            timeout = MAX_INT

        user_org = (self.user, self.remote_user_map['org'])
        # Clean up
        self.kwargs.pop('user_org', None)
        self.kwargs.pop('section', None)
        self.kwargs.pop('section', None)
        self.kwargs.pop('tgt_args', None)

        user_libs = []
        if 'includes' in self.kwargs:
            try:
                # process runtime includes
                for lib in self.kwargs['includes']:
                    user_libs.append(lib)
            except Exception, ex:
                LOG.exception(ex)

        # start_time = time.time()

        for step_id, section in enumerate(self.sections):
            libs = []
            if user_libs:
                libs.extend(user_libs)

            ts = time.mktime(time.gmtime())
            message = InitialMessage(session_id=self.session_id,
                                     ts=ts,
                                     org=user_org[1], step_id=step_id)
            self._reply(message)
            msg_ret = []

            try:
                """
                for plugin in self.plugin_context.job_plugins:
                    try:
                        # Save passed env for job
                        (data, env) = plugin().before(user_org,
                                                      self.session_id,
                                                      section.data,
                                                      env,
                                                      section.args,
                                                      self.plugin_context,
                                                      **self.kwargs)
                        if data:
                            # updated
                            section.data = data

                    except InterruptStep:
                        LOG.warn("BEFORE: Step execution interrupted by %s" %
                                 plugin.__name__)
                        raise
                    except InterruptExecution:
                        LOG.warn(
                            "BEFORE: Session execution interrupted by %s" %
                            plugin.__name__)
                        raise
                    except Exception, ex:
                        LOG.error('Plugin error(%s):  %r' % (plugin, ex))

                for plugin in self.plugin_context.lib_plugins:
                    try:
                        _libs = plugin().process(user_org,
                                                 section.data,
                                                 env,
                                                 section.args)
                        for lib in _libs:
                            libs.append(lib)
                    except Exception, ex:
                        LOG.error('Plugin error(%s):  %r' % (plugin, ex))
                """
                if section.args and section.args.timeout:
                    try:
                        timeout = int(section.args.timeout)
                    except ValueError:
                        pass

                section.update_targets(env)
                #
                # Exec section
                #

                section_it = self.exec_section(
                    section.targets, dict(env=env, script=section.data,
                                          remote_user_map=self.remote_user_map,
                                          libs=libs), timeout=timeout)
                for _reply in section_it:
                    if _reply[0] == 'PIPE':
                        # reply: 'PIPE', job_id, run_as, node_id, stdout,
                        # stderr

                        # reply-fwd: session_id, PIPEOUT, session_id, time,
                        #   task_name, user, job_id, run_as,
                        #   node_id, stdout, stderr
                        names = ("job_id", "run_as", "node",
                                 "stdout", "stderr")
                        ts = time.mktime(time.gmtime())
                        message = PipeMessage(session_id=self.session_id,
                                              step_id=step_id,
                                              user=self.user,
                                              org=self.remote_user_map['org'],
                                              ts=ts,
                                              **dict(zip(names, _reply[1:])))
                        self._reply(message)
                    else:
                        job_id, msg_ret = _reply
                        break

                new_env = {}
                for _ret in msg_ret:
                    _env = _ret['env']
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
                """
                for plugin in self.plugin_context.job_plugins:
                    try:
                        # Save passed env for job
                        plugin().after(
                            user_org, self.session_id, job_id, env, msg_ret,
                            section.args, self.plugin_context, **self.kwargs)
                    except InterruptStep:
                        LOG.warn("AFTER: Step execution interrupted by %s" %
                                 plugin.__name__)
                        raise
                    except InterruptExecution:
                        LOG.warn("AFTER: Session execution interrupted by %s" %
                                 plugin.__name__)
                        raise
                    except Exception, ex:
                        LOG.error('Plugin error(%s):  %r' % (plugin, ex))
                """
                ret.append(dict(targets=section.targets,
                                jobid=job_id,
                                args=section.args_string,
                                response=msg_ret))

            except InterruptStep:
                continue
            except InterruptExecution:
                break
            except Exception, ex:
                LOG.exception(ex)
                continue
            finally:
                exec_result = [dict(node=node['node'],
                                    run_as=node['remote_user'],
                                    ret_code=node['ret_code'])
                               for node in msg_ret]
                ts = time.mktime(time.gmtime())
                message = FinishedMessage(session_id=self.session_id,
                                          ts=ts,
                                          user=self.user,
                                          step_id=step_id,
                                          org=self.remote_user_map['org'],
                                          result=exec_result,
                                          env=env)
                self._reply(message)

        self.session_event.set()

        # Wait for all other threads to finish consuming session data
        time.sleep(.5)
        self.job_done.close()

    def exec_section(self, targets, request, timeout=None):
        """
        Send request to nodes
        Arguments:

        targets     --  Target nodes, described by Id or Selector

        request     --  Job request

        timeout     --  Wait timeout for the request in seconds.
                        Defaults to config value or 300 sec

        """

        job_id = uuid.uuid4().hex  # Job Session id

        self.manager.register_session(job_id)
        job_event = Event()
        remote_user_map = request.pop('remote_user_map')
        # Call for nodes
        job_queue = self.manager.backend.consume_queue('in_messages',
                                                       ident=job_id)
        job_reply = self.manager.backend.publish_queue('out_messages')
        user_input_queue = self.manager.backend.consume_queue('user_input',
                                                              ident=job_id)

        poller = self.manager.backend.create_poller(job_queue,
                                                    user_input_queue)
        node_map = {}
        discovery_period = time.time() + self.manager.discovery_timeout
        total_wait = time.time() + (timeout or self.manager.wait_timeout)

        target = JobTarget(job_id, str(targets))
        target.hdr.org = remote_user_map['org']
        self.manager.publisher.send(target._)

        user_map = UserMap(remote_user_map['roles'], self.user)

        try:
            while not self.session_event.is_set() and not job_event.is_set():
                ready = poller.poll(500)

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
                                  Input.build(job_id,
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
                        LOG.warn('Timeout waiting for response from nodes')
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
                if (self.manager.config.security.use_org and
                        job_rep.hdr.org != remote_user_map['org']):
                    continue

                state = node_map.setdefault(
                    job_rep.hdr.peer, dict(status=StatusCodes.STARTED,
                                           data={},
                                           stdout='',
                                           stderr=''))

                node_map[job_rep.hdr.peer]['router_id'] = job_rep.hdr.ident
                if isinstance(job_rep, Ready):
                    remote_user = user_map.select(job_rep.hdr.peer)
                    if not remote_user:
                        LOG.info("Node %s not allowed for user %s" % (
                            job_rep.hdr.peer,
                            self.user))
                        node_map.pop(job_rep.hdr.peer)
                        continue
                    # Send task to attached node
                    node_map[job_rep.hdr.peer]['remote_user'] = remote_user
                    LOG.info("Sending job to %s" % job_rep.hdr.peer)
                    job_msg = Job(job_id, remote_user, request)
                    job_msg.hdr.ident = job_rep.hdr.ident
                    job_msg.hdr.dest = job_id
                    job_reply.send(job_msg._)
                    continue

                state['status'] = job_rep.control

                if isinstance(job_rep, Finished):
                    state['data']['ret_code'] = job_rep.result['ret_code']
                    state['data']['env'] = job_rep.result['env']
                    if job_rep.result['stdout'] or job_rep.result['stderr']:
                        yield ('PIPE', job_id,
                               '',
                               job_rep.hdr.peer,
                               job_rep.result['stdout'],
                               job_rep.result['stderr'])
                elif isinstance(job_rep, StdOut):
                    yield ('PIPE', job_id,
                           job_rep.run_as,
                           job_rep.hdr.peer,
                           job_rep.output, '')
                elif isinstance(job_rep, StdErr):
                    yield ('PIPE', job_id,
                           job_rep.run_as,
                           job_rep.hdr.peer,
                           '', job_rep.output)
                elif isinstance(job_rep, Events):
                    LOG.info("Polling events for %s" % job_id)
                # else:
                #    job_reply.send(job_rep.ident, job_rep.peer, job_id,
                #    'UNKNOWN')

                LOG.debug('Resp[%s]:: [%s][%s]' % (job_id,
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
                        job_msg = Term(job_id, self.stop_reason)
                        job_msg.hdr.ident = node['router_id']
                        job_msg.hdr.dest = job_id
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

                        node['stdout'] = str(node)

                        yield ('PIPE', job_id, '', name,
                               node['stdout'], node['stderr'])

            job_event.set()

        user_input_queue.close()
        job_queue.close()
        job_reply.close()
        self.manager.delete_session(job_id)

        yield job_id, [dict(node=k,
                            remote_user=n['remote_user'],
                            job_id=job_id,
                            env=n['data'].get('env', {}),
                            stdout=n['data'].get('stdout', ''),
                            stderr=n['data'].get('stderr', ''),
                            ret_code=n['data'].get('ret_code', -255))
                       for k, n in node_map.items()]


class Section(object):

    def __init__(self):
        self.targets = ""

    def update_targets(self, env):
        params = parser.has_params(self.targets)
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
                    self.targets = self.targets.replace(
                        sel + param, repl_params)


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
