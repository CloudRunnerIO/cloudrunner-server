import json
import logging
from sys import maxint as MAX_INT
from threading import (Thread, Event)
import time
import zmq
import uuid

from cloudrunner.core import parser
from cloudrunner.core.exceptions import ConnectionError
from cloudrunner.core.message import JobInput
from cloudrunner.core.message import JobRep
from cloudrunner.core.message import StatusCodes

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

    def _reply(self, session_id, ret_type, data):
        for sub in self.manager.subscriptions.get(session_id, []):
            try:
                self.job_done.send(
                    *[sub.peer, ret_type] + [str(x) for x in data])
            except zmq.ZMQError as e:
                if self.manager.context.closed or zerr.errno == zmq.ETERM \
                        or zerr.errno == zmq.ENOTSOCK:
                    break
            except ConnectionError:
                break

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
        env = self.kwargs.pop('env', {})
        self.parse_script(env)
        self.job_done = self.manager.backend.publish_queue('finished_jobs')

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

        tags = json.dumps(self.kwargs.get("tags", []))

        user_org = (self.user, self.remote_user_map.org)

        # Clean up
        self.kwargs.pop('user_org', None)
        self.kwargs.pop('section', None)
        self.kwargs.pop('section', None)
        self.kwargs.pop('tgt_args', None)

        user_libs = []
        if 'includes' in self.kwargs:
            try:
                # process runtime includes
                for name, source in self.kwargs['includes'].items():
                    user_libs.append(dict(name=name, source=source))
            except Exception, ex:
                LOG.exception(ex)

        start_time = time.time()

        for section in self.sections:
            libs = user_libs

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

            if section.args.timeout:
                try:
                    timeout = int(section.args.timeout)
                except ValueError:
                    pass

            section.update_targets(env)
            msg_ret = []
            #
            # Exec section
            #

            section_it = self.exec_section(
                section.targets, dict(env=env, script=section.data,
                                      remote_user_map=self.remote_user_map,
                                      libs=libs), timeout=timeout)
            for _reply in section_it:
                if _reply[0] == 'PIPE':
                    job_id = _reply[1]
                    run_as = str(_reply[2])
                    args = _reply[3:]
                    meta = [str(int(time.time())), self.task_name, self.user,
                            self.remote_user_map.org, section.targets, tags]

                    # reply: 'PIPE', job_id, run_as, node_id, stdout, stderr
                    # reply-fwd: session_id, PIPEOUT, session_id, time,
                    #   task_name, user, targets, tags, job_id, run_as,
                    #   node_id, stdout, stderr

                    self._reply(self.session_id, StatusCodes.PIPEOUT,
                                [self.session_id] + meta + list(_reply[1:]))
                else:
                    job_id, msg_ret = _reply

            new_env = {}
            for _ret in msg_ret:
                _env = _ret['env']
                for k, v in _env.items():
                    if k in new_env:
                        if not isinstance(new_env[k], list):
                            new_env[k] = [new_env[k]]
                        if isinstance(v, list):
                            new_env[k].extend(v)
                        else:
                            new_env[k].append(v)
                    else:
                        new_env[k] = v

            env.update(new_env)

            for plugin in self.plugin_context.job_plugins:
                try:
                    # Save passed env for job
                    plugin().after(
                        user_org, self.session_id, job_id, env, msg_ret,
                        section.args, self.plugin_context, **self.kwargs)
                except Exception, ex:
                    LOG.error('Plugin error(%s):  %r' % (plugin, ex))

            ret.append(dict(targets=section.targets,
                            jobid=job_id,
                            args=section.args_string,
                            response=msg_ret))

        response = []
        for run in ret:
            nodes = run['response']
            exec_result = [dict(node=node['node'], run_as=node['remote_user'],
                                ret_code=node['ret_code']) for node in nodes]
            response.append(dict(targets=run['targets'],
                                 jobid=run['jobid'],
                                 args=run['args'],
                                 nodes=exec_result))

        meta = [self.session_id, str(int(time.time())),
                self.task_name, self.user, self.remote_user_map.org, tags]
        self._reply(self.session_id, StatusCodes.FINISHED,
                    meta + [self.payload, json.dumps(response)])

        self.session_event.set()
        del self.manager.subscriptions[self.session_id]
        del self.manager.sessions[self.session_id]

        # Wait for all other threads to finish consuming session data
        time.sleep(2)
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

        job_id = str(uuid.uuid1())  # Job Session id
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

        self.manager.publisher.send(
            remote_user_map.org, job_id, str(targets))
        yield ('PIPE', job_id, str(targets), 'Job Started')

        try:
            while not self.session_event.is_set() and not job_event.is_set():
                ready = poller.poll(500)

                if user_input_queue in ready:
                    frames = user_input_queue.recv()

                    # input from user -> node
                    input_req = JobInput.build(*frames)
                    if not input_req:
                        LOG.warn("Invalid request %s" % frames)
                        continue

                    for node, data in node_map.items():
                        if input_req.cmd == 'INPUT' and \
                            (input_req.targets == '*' or
                                node in input_req.targets):
                            job_reply.send(data['router_id'], node, job_id,
                                           input_req.cmd, input_req.data)
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

                job_rep = JobRep.build(*frames)

                if not job_rep:
                    LOG.error("Invalid reply from node: %s" % frames)
                    continue

                # Assert we have rep from the same organization
                if self.manager.config.security.use_org:
                    assert job_rep.org == remote_user_map.org, \
                        job_rep.org + " != " + remote_user_map.org

                state = node_map.setdefault(
                    job_rep.peer, dict(status=StatusCodes.STARTED,
                                       data={},
                                       stdout='',
                                       stderr=''))

                node_map[job_rep.peer]['router_id'] = job_rep.ident
                if job_rep.control == StatusCodes.READY:
                    remote_user = remote_user_map.select(job_rep.peer)
                    if not remote_user:
                        LOG.info("Node %s not allowed for user %s" % (
                            job_rep.peer,
                            remote_user_map.owner))
                        node_map.pop(job_rep.peer)
                        continue
                    # Send task to attached node
                    node_map[job_rep.peer]['remote_user'] = remote_user
                    LOG.info("Sending job to %s" % job_rep.peer)
                    job_reply.send(job_rep.ident, job_rep.peer, job_id, 'JOB',
                                   json.dumps((remote_user, request)))
                    continue

                if not job_rep.data:
                    continue

                state['data'].update(job_rep.data)
                state['status'] = job_rep.control
                if job_rep.control == StatusCodes.FINISHED:
                    #job_reply.send(job_rep.ident, job_rep.peer, job_id, 'ACK')
                    state['data']['stdout'] = state['stdout'] + \
                        state['data']['stdout']
                    state['data']['stderr'] = job_rep.data.pop('stderr')
                    if state['data']['stdout'] and state['data']['stderr']:
                        yield ('PIPE', job_id,
                               job_rep.run_as,
                               job_rep.peer,
                               state['data']['stdout'],
                               state['data']['stderr'])
                elif job_rep.control == StatusCodes.STDOUT:
                    yield ('PIPE', job_id,
                           job_rep.run_as,
                           job_rep.peer,
                           job_rep.data['stdout'], '')
                elif job_rep.control == StatusCodes.STDERR:
                    yield ('PIPE', job_id,
                           job_rep.run_as,
                           job_rep.peer,
                           '', job_rep.data['stderr'])
                elif job_rep.control == StatusCodes.EVENTS:
                    LOG.info("Polling events for %s" % job_id)
                # else:
                #    job_reply.send(job_rep.ident, job_rep.peer, job_id,
                #    'UNKNOWN')

                LOG.debug('Resp[%s]:: [%s][%s][%s]\n' % (job_id,
                                                         job_rep.peer,
                                                         job_rep.control,
                                                         job_rep.data))
        except ConnectionError:
            # Transport died
            self.session_event.set()
        except Exception, ex:
            LOG.exception(ex)
        finally:
            if self.session_event.is_set() or job_event.is_set():
                # Forced stop ?
                # ToDo: check arg flag to keep task running
                for name, node in node_map.items():
                    try:
                        job_reply.send(
                            node['router_id'], name, job_id,
                            'TERM', self.stop_reason)
                    except:
                        continue

                # Wait for jobs to finalize
                job_event.wait(1)
                for name, node in node_map.items():
                    if node['status'] != StatusCodes.FINISHED:
                        node['status'] = StatusCodes.FINISHED
                        node['stderr'] = \
                            node['data'].setdefault('stderr', '') + \
                            'Job execution stopped: [%s]' % self.stop_reason
                        yield ('PIPE', job_id, job_rep.run_as, name,
                               node['stdout'], node['stderr'])

            job_event.set()

        user_input_queue.close()
        job_queue.close()
        job_reply.close()

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
