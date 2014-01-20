#!/usr/bin/python
# -*- coding: utf-8 -*-
# vim: tabstop=4 shiftwidth=4 softtabstop=4
# PYTHON_ARGCOMPLETE_OK

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

try:
    import argcomplete
except ImportError:
    pass
import argparse
import json
import logging
import os
import signal
import sys
import time
import threading
import uuid
import zmq
from zmq.eventloop import ioloop
from zmq.devices.monitoredqueue import monitored_queue

from cloudrunner import CONFIG_LOCATION
from cloudrunner import LOG_LOCATION
from cloudrunner.util.config import Config
from cloudrunner.util.crypto import hash_token
from cloudrunner.util.logconfig import configure_loggers

CONFIG = Config(CONFIG_LOCATION)

if CONFIG.verbose_level:
    configure_loggers(getattr(logging, CONFIG.verbose_level, 'INFO'),
                      LOG_LOCATION)
else:
    configure_loggers(logging.DEBUG if CONFIG.verbose else logging.INFO,
                      LOG_LOCATION)

from cloudrunner.core import message
from cloudrunner.core.message import StatusCodes
from cloudrunner.core import parser
from cloudrunner.util.daemon import Daemon
from cloudrunner.util.loader import load_plugins
from cloudrunner.util.loader import local_plugin_loader
from cloudrunner.util.shell import colors

from cloudrunner_server.dispatcher import SCHEDULER_URI_TEMPLATE
from cloudrunner_server.dispatcher import PluginContext
from cloudrunner_server.dispatcher import Promise
from cloudrunner_server.dispatcher.admin import Admin
from cloudrunner_server.dispatcher.publisher import Publisher
from cloudrunner_server.master.functions import CertController
from cloudrunner_server.plugins import PLUGIN_BASES
from cloudrunner_server.plugins.args_provider import ArgsProvider
from cloudrunner_server.plugins.args_provider import CliArgsProvider
from cloudrunner_server.plugins.args_provider import ManagedPlugin
from cloudrunner_server.plugins.auth.base import AuthPluginBase
from cloudrunner_server.plugins.jobs.base import JobInOutProcessorPluginBase
from cloudrunner_server.plugins.libs.base import IncludeLibPluginBase

SCHEDULER_URI = SCHEDULER_URI_TEMPLATE % CONFIG

LOG = logging.getLogger("Dispatcher")


class Dispatcher(Daemon):

    """
        Main dispatcher. Receives requests from clients
        and runs them on the specified nodes
    """

    def __init__(self, *_args, **kwargs):
        arg_parser = argparse.ArgumentParser()

        pidfile = arg_parser.add_argument('-p', '--pidfile',
                                          dest='pidfile',
                                          help='Daemonize process with the '
                                               'given pid file')
        config = arg_parser.add_argument('-c', '--config',
                                         help='Config file')
        run_action = arg_parser.add_argument(
            'action', choices=['start', 'stop', 'restart', 'run'],
            help='Apply action on the daemonized process\n'
            'For the actions [start, stop, restart] - pass a pid file\n'
            'Run - start process in debug mode\n')

        try:
            argcomplete.autocomplete(arg_parser)
        except:
            pass

        if _args:
            self.args = arg_parser.parse_args(_args)
        else:
            self.args = arg_parser.parse_args()

        if self.args.pidfile:
            super(Dispatcher, self).__init__(self.args.pidfile,
                                             stdout='/tmp/log')
        elif self.args.action in ['start', 'stop', 'restart']:
            print colors.red("The --pidfile option is required"
                             " with [start, stop, restart] commands",
                             bold=1)
            exit(1)

        global CONFIG
        if 'config' in kwargs:
            CONFIG = kwargs['config']
        elif self.args.config:
            CONFIG = Config(self.args.config)

    def init_libs(self):
        self.dispatcher_uri = ''.join(['tcp://',
                                      CONFIG.listen_uri or '0.0.0.0:38123'])
        self.worker_uri = 'inproc://cr-dispatcher-workers'
        self.worker_out_uri = 'inproc://cr-dispatcher-workers-out'
        self.job_done_uri = 'inproc://cr-dispatcher-done'
        self.scheduler_uri = SCHEDULER_URI
        self.logger_uri = CONFIG.logger_uri or \
            "ipc://%(sock_dir)s/logger.sock" % CONFIG
        self.logger_uri_int = "inproc://logger-int"

        # instantiate dispatcher implementation
        self.transport_class = local_plugin_loader(CONFIG.transport)
        if not self.transport_class:
            LOG.fatal('Cannot find transport class. Set it in config file.')
            exit(1)

        load_plugins(CONFIG)

        args_plugins = argparse.ArgumentParser(add_help=False)
        self.plugin_plugins = argparse.ArgumentParser(add_help=False).\
            add_subparsers(dest='plugins')

        self.plugin_register = {}
        self.plugin_cli_register = {}
        for plugin_base in PLUGIN_BASES:
            for plugin in plugin_base.__subclasses__():

                if issubclass(plugin, ArgsProvider):
                    try:
                        _args = plugin().append_args()
                        if not isinstance(_args, list):
                            _args = [_args]

                        for _d in _args:
                            arg = _d.pop('arg')
                            args_plugins.add_argument(arg, **_d)
                            self.plugin_register.setdefault(arg,
                                                            []).append(plugin)
                    except Exception, ex:
                        LOG.exception(ex)
                        continue

                if issubclass(plugin, CliArgsProvider):
                    try:
                        arg = plugin().append_cli_args(self.plugin_plugins)
                        self.plugin_cli_register.setdefault(arg,
                                                            []).append(plugin)
                    except Exception, ex:
                        LOG.exception(ex)
                        continue

                if issubclass(plugin, ManagedPlugin):
                    try:
                        plugin().start()
                    except Exception, ex:
                        LOG.error('Plugin error(%s):  %r' % (plugin, ex))

        self.scheduler_class = None
        if CONFIG.scheduler:
            self.scheduler_class = local_plugin_loader(CONFIG.scheduler)
            LOG.info('Loaded scheduler class: %s .' % self.scheduler_class)
        else:
            LOG.warn('Cannot find scheduler class. Set it in config file.')

        if AuthPluginBase.__subclasses__():
            self.auth_klass = AuthPluginBase.__subclasses__()[0]
        else:
            if not CONFIG.auth:
                LOG.warn('No Auth plugin found')
            else:
                self.auth_klass = local_plugin_loader(CONFIG.auth)

        self.config = CONFIG
        self.auth = self.auth_klass(self.config)

        self.plugin_context = PluginContext(self.auth)

        self.plugin_context.args_plugins = args_plugins
        if JobInOutProcessorPluginBase.__subclasses__():
            job_plugins = JobInOutProcessorPluginBase.__subclasses__()
            LOG.info('Loading Job PRocessing plugins: %s' % job_plugins)
        else:
            job_plugins = []
        self.plugin_context.job_plugins = job_plugins

        if IncludeLibPluginBase.__subclasses__():
            lib_plugins = IncludeLibPluginBase.__subclasses__()
            LOG.info('Loading Lib Save plugins: %s' % lib_plugins)
        else:
            lib_plugins = []
        self.plugin_context.lib_plugins = lib_plugins

    def _login(self, auth_type=1):
        LOG.debug("[Login][%s]: %s" % (auth_type, self.user_id))

        if auth_type == 1:
            # Password
            return self.auth.authenticate(self.user_id, self.user_token)
        else:
            # Token
            return self.auth.validate(self.user_id, self.user_token)

    # Actions
    def check_login(self, user, remote_user_map, **kwargs):
        return True  # Already logged, kind of echo

    def get_api_token(self, *args, **kwargs):
        token = self.auth.create_token(self.user_id, **kwargs)
        if token:
            return ["TOKEN", token]
        else:
            return ["FAILURE"]

    def plugins(self, payload, remote_user_map, **kwargs):
        plug = [(args, [c.__module__ for c in p])
                for (args, p) in sorted(self.plugin_register.items(),
                                        key=lambda x: (x[1], x[0]))]

        cli_plug = [(args, [c.__module__ for c in p])
                    for (args, p) in sorted(self.plugin_cli_register.items(),
                                            key=lambda x: (x[1], x[0]))]
        return [plug, cli_plug]

    def plugin(self, payload, remote_user_map, **kwargs):
        resp = []
        plugin_name = kwargs['plugin']
        plugins = self.plugin_cli_register.get(plugin_name, None)
        if not plugins:
            return ['Plugin %s not found' % plugin_name]

        user_org = (self.user_id, remote_user_map.org)

        for plugin in plugins:
            try:
                ret = plugin().call(user_org, payload, kwargs.get('args', ''))
                if ret:
                    resp.append(ret)
            except Exception, ex:
                LOG.error(ex)

        return resp

    def schedule(self, payload, remote_user_map, **kwargs):
        if not self.scheduler_class:
            return [False, 'ERROR: Scheduler not defined in config']

        action = kwargs['action']

        kwargs['payload'] = payload
        if action == "add":
            # Set auth token
            kwargs['auth_token'] = self.get_api_token(expiry=-1)[1]

        bin_path = os.path.dirname(os.path.abspath(sys.argv[0]))
        kwargs['exec'] = os.path.join(bin_path, 'cloudrunner-master')

        scheduler = self.scheduler_class()
        (success, msg) = getattr(scheduler, action)(self.user_id,
                                                    **kwargs)
        return (success, msg)

    def list_nodes(self, payload, remote_user_map, **kwargs):
        cert = CertController(CONFIG)
        org = remote_user_map.org if self.config.security.use_org else None
        nodes = cert.get_approved_nodes(org)
        return (True, [node for node in nodes])

    def list_pending_nodes(self, payload, remote_user_map, **kwargs):
        cert = CertController(CONFIG)
        org = remote_user_map.org if self.config.security.use_org else None
        nodes = cert.list_pending(org)
        return (True, [node for node in nodes])

    def list_active_nodes(self, payload, remote_user_map, **kwargs):
        req_sock = self.context.socket(zmq.SUB)
        req_sock.connect(self.transport.mngmt_uri)
        req_sock.setsockopt(zmq.SUBSCRIBE, str(remote_user_map.org))
        time.sleep(.5)
        # invoke heartbeat printer
        os.kill(self.transport.publisher.pid, signal.SIGHUP)

        if req_sock.poll(500):
            nodes = req_sock.recv_multipart()
            assert nodes[0] == remote_user_map.org
            active_nodes = nodes[1:]
        else:
            active_nodes = ['Cannot retrieve nodes']
        req_sock.close()

        return (True, active_nodes)

    def library(self, payload, remote_user_map, **kwargs):
        success, result = False, ''
        user_org = (self.user_id, remote_user_map.org)

        for plugin in self.plugin_context.lib_plugins:
            try:
                action = kwargs.pop('action')
                args = []
                if action == "add":
                    args.append(kwargs.pop('name'))
                    args.append(payload)
                success, result = getattr(plugin(), action)(user_org,
                                                            *args,
                                                            **kwargs)
            except Exception, ex:
                LOG.exception(ex)
                return False, "Cannot process command, see logs for details"

        return success, result

    def attach(self, payload, remote_user_map, **kwargs):
        """
        Attach to an existing pre-defined session
        or create it if not started yet
        """
        (targets, req_args) = parser.parse_selectors(payload)
        promise = Promise(kwargs.get('session_id'))
        promise.targets = targets
        return promise

    def detach(self, payload, remote_user_map, **kwargs):
        """
        Detach from an existing pre-defined session
        """
        promise = Promise(kwargs.get('session_id'))
        promise.remove = True
        return promise

    def notify(self, payload, remote_user_map, **kwargs):
        session_id = str(kwargs.pop('session_id'))
        job_id = str(kwargs.pop('job_id'))

        targets = str(kwargs.pop('targets', '*'))
        session = [sess for sess in self.publisher.subscriptions.get(
            session_id, []) if sess.owner == self.user_id]
        if not session:
            return [False, "You are not the owner of the session"]
        # return [True, 'Jobs notified']
        self.notification_service.send_multipart(
            [job_id, '', 'INPUT', session_id, self.user_id,
             str(remote_user_map.org), payload, targets])
        return [True, "Notified"]

    def term(self, payload, remote_user_map, **kwargs):
        session_id = str(kwargs.pop('session_id'))

        session_sub = [sess for sess in self.publisher.subscriptions.get(
            session_id, []) if sess.owner == self.user_id]
        if not session_sub:
            return [False, "You are not the owner of the session"]

        session = self.publisher.sessions.get(session_id)
        if session:
            session.stop_reason = str(kwargs.get('action', 'term'))
            session.stopped.set()
            return [True, "Session terminated"]
        else:
            return [False, "Session not found"]

    def dispatch(self, payload, remote_user_map, **kwargs):
        """
        Dispatch script to targeted nodes
        """

        session_id = str(uuid.uuid1())

        promise = self.publisher.prepare_session(self.user_id, session_id,
                                                 payload, remote_user_map,
                                                 plugin_ctx=self.plugin_context,
                                                 **kwargs)
        promise.main = True
        return promise

    def worker(self, *args):
        job_queue = self.context.socket(zmq.DEALER)
        job_done_queue = self.context.socket(zmq.DEALER)
        job_done_queue.connect(self.worker_out_uri)

        log_queue = self.context.socket(zmq.PUB)
        log_queue.connect(self.logger_uri_int)

        try:
            job_queue.connect(self.worker_uri)
        except zmq.ZMQError, zerr:
            if zerr.errno == 2:
                # Socket dir is missing
                LOG.error("Socket uri is missing: %s" % self.worker_uri)
                exit(1)

        poller = zmq.Poller()
        poller.register(job_queue, zmq.POLLIN)
        poller.register(job_done_queue, zmq.POLLIN)

        while not self.stopping.is_set():
            ready = {}
            try:
                frames = None
                try:
                    ready = dict(poller.poll(300))
                    if not ready:
                        continue
                except zmq.ZMQError as e:
                    if context.closed or zerr.errno == zmq.ETERM \
                        or zerr.errno == zmq.ENOTSOCK:
                        break
                    LOG.exception(e)
                    if not self.stopping.is_set():
                        continue
                if job_queue in ready:
                    # User -> queue
                    frames = job_queue.recv_multipart()
                    sender = frames.pop(0)
                    req = message.AgentReq.build(*frames)
                    if not req:
                        LOG.error("Invalid request %s" % frames)
                        continue

                    if req.control.startswith('_'):
                        LOG.error("Invalid request %s" % frames)
                        continue

                    if not hasattr(self, req.control):
                        # TODO: Check if a plugin supports command
                        job_queue.send_multipart(
                            [sender, StatusCodes.FINISHED,
                             json.dumps(
                             ["ERROR: [%s] command not available on Master" %
                              req.control])])
                        continue

                    self.user_id = req.login
                    if req.auth_type == 1:
                        # Password auth
                        self.user_token = hash_token(req.password)
                    else:
                        # Token auth
                        self.user_token = req.password

                    auth_check = self._login(req.auth_type)
                    if not auth_check[0]:
                        job_queue.send_multipart([sender, 'NOT AUTHORIZED'])
                        continue

                    remote_user_map = auth_check[1]
                    LOG.info('action: %s, user: %s/%s' % (req.control,
                                                          req.login,
                                                          remote_user_map.org))
                    # def pipe_callback(*args):
                    #    self.job_queue.send_multipart(
                    #        [sender, StatusCodes.PIPEOUT,
                    #         json.dumps(args)])

                    response = getattr(self, req.control)(req.data,
                                                          remote_user_map,
                                                          **req.kwargs)
                    if isinstance(response, Promise):
                        response.peer = sender
                        if response.main:
                            response.resolve()
                        elif response.remove:
                            # Detach
                            try:
                                for sub in self.publisher.subscriptions[
                                    response.session_id]:
                                    if sub.session_id == response.session_id:
                                        self.publisher.subscriptions[
                                            response.session_id].remove(sub)
                                        break
                            except:
                                pass
                        else:
                            self.publisher.subscriptions[
                                response.session_id].append(response)
                    elif response:
                        job_queue.send_multipart(
                            [sender, StatusCodes.FINISHED,
                             json.dumps(response)])

                elif job_done_queue in ready:
                    # Done -> user
                    frames = job_done_queue.recv_multipart()
                    job_queue.send_multipart(frames)
                    log_queue.send_multipart(frames[1:])
            except zmq.ZMQError, err:
                if self.context.closed or \
                        getattr(err, 'errno', 0) == zmq.ETERM:
                    # System interrupt
                    break
                LOG.exception(err)

        job_queue.close()
        LOG.info('Server worker exited')

    def sched_worker(self, *args):
        worker_thread = self.context.socket(zmq.DEALER)
        try:
            worker_thread.bind(self.scheduler_uri)
        except zmq.ZMQError, zerr:
            if zerr.errno == 2:
                # Socket dir is missing
                LOG.error("Socket uri is missing: %s" % self.scheduler_uri)
                exit(1)

        while not self.stopping.is_set():
            try:
                frames = None
                try:
                    frames = worker_thread.recv_multipart(zmq.NOBLOCK)
                except zmq.ZMQError as e:
                    if e.errno != zmq.EAGAIN:
                        raise
                    if not self.stopping.is_set():
                        time.sleep(.1)
                        continue
                    else:
                        if not frames:
                            break

                req = message.ScheduleReq.build(*frames)
                if not req:
                    LOG.error('Invalid request: %s' % frames)
                    continue

                LOG.info('action: %s, sched job: %s' %
                         (req.control, req.job_id))

                scheduler = self.scheduler_class()
                job = scheduler.get(req.job_id)

                if not job:
                    LOG.error("No job found for id: %s" % req.job_id)
                    continue
                try:
                    payload = open(job.file).read()
                except Exception, ex:
                    LOG.error("Cannot load schedule job %s" % job.name)
                    LOG.exception(ex)
                    continue

                self.user_id = job.user
                self.user_token = job.token  # Already hashed

                auth_check = self._login(auth_type=2)

                if not auth_check[0]:
                    LOG.error('Job %s@%s - NOT AUTHORIZED' % (job.user,
                                                              job.id))
                    continue

                remote_user_map = auth_check[1]

                LOG.info('Starting scheduled job %s(%s)@%s' % (job.user,
                                                               remote_user_map,
                                                               job.name))
                response = self.dispatch(payload, remote_user_map,
                                         caller='Scheduler: %s' % job.name)
                if isinstance(response, Promise):
                    response.peer = ''
                    response.resolve()

            except zmq.ZMQError, err:
                if self.context.closed or \
                        getattr(err, 'errno', 0) == zmq.ETERM:
                    # System interrupt
                    break
                LOG.exception(err)

        worker_thread.close()
        LOG.info('Scheduler worker exited')

    def choose(self):
        getattr(self, self.args.action)()

    def run(self):

        self.init_libs()
        self.transport = self.transport_class(self.config)

        if not self.config.sock_dir:
            # try to create it
            raise Exception("Socket dir (sock_dir) is not set in config")
        if not os.path.exists(self.config.sock_dir):
            try:
                os.makedirs(self.config.sock_dir)
            except:
                raise Exception("Socket dir doesn't exist and "
                                "cannot be created")

        WORKER_COUNT = int(CONFIG.workers_count or 10)
        SCHED_WORKER_COUNT = int(CONFIG.sched_worker_count or 5)

        self.context = zmq.Context(3)
        self.stopping = threading.Event()

        if self.config.security.use_org:
            self.transport.publisher.organizations = self.auth.list_orgs()
        else:
            self.transport.publisher.organizations = \
                [self.transport.DEFAULT_ORG]
        self.transport.run()  # Run router

        self.admin = Admin(self.config, self.transport.admin)
        self.admin.start()

        time.sleep(.5)

        self.publisher = Publisher(self.config, self.context,
                                   self.transport.publisher,
                                   self.job_done_uri,
                                   plugins_ctx=self.plugin_context)
        self.publisher.start()

        def input_device():
            worker_proxy = self.context.socket(zmq.DEALER)
            worker_proxy.bind(self.worker_uri)
            router = self.context.socket(zmq.ROUTER)
            router.bind(self.dispatcher_uri)
            try:
                zmq.device(zmq.QUEUE, router, worker_proxy)
            except zmq.ZMQError, err:
                if self.context.closed or \
                        getattr(err, 'errno', 0) == zmq.ETERM or \
                        getattr(err, 'errno', 0) == zmq.ENOTSOCK:
                    # System interrupt
                    pass
                else:
                    raise err
            router.close()
            worker_proxy.close()

        def output_device():
            job_done = self.context.socket(zmq.DEALER)
            job_done.bind(self.job_done_uri)
            worker_out_proxy = self.context.socket(zmq.DEALER)
            worker_out_proxy.bind(self.worker_out_uri)
            # For use of monitoring proxy
            # mon_proxy = self.context.socket(zmq.PUB)
            # mon_proxy.bind(self.mon_proxy_uri)
            # LOG.info("Monitor writing on %s" % self.mon_proxy_uri)
            try:
                zmq.device(zmq.QUEUE, worker_out_proxy, job_done)
                # monitored_queue(worker_out_proxy, job_done, mon_proxy)
            except zmq.ZMQError, err:
                if self.context.closed or \
                        getattr(err, 'errno', 0) == zmq.ETERM or \
                        getattr(err, 'errno', 0) == zmq.ENOTSOCK:
                    # System interrupt
                    pass
                else:
                    raise err
            job_done.close()
            worker_out_proxy.close()
            # mon_proxy.close()

        def logger_device():
            log_xsub = self.context.socket(zmq.XSUB)
            log_xsub.bind(self.logger_uri_int)
            log_xpub = self.context.socket(zmq.XPUB)
            log_xpub.bind(self.logger_uri)
            while True:
                try:
                    zmq.device(zmq.FORWARDER, log_xsub, log_xpub)
                except zmq.ZMQError, err:
                    if self.context.closed or \
                            getattr(err, 'errno', 0) == zmq.ETERM:
                        # System interrupt
                        break
                    LOG.exception(err)
                    continue

        self.notification_service = self.context.socket(zmq.ROUTER)
        self.notification_service.bind(self.transport.notify_msg_bus_uri)

        device_in = threading.Thread(target=input_device)
        device_in.start()

        device_out = threading.Thread(target=output_device)
        device_out.start()

        device_log = threading.Thread(target=logger_device)
        device_log.start()

        # wait for devices
        time.sleep(.5)

        self.threads = []
        for i in range(WORKER_COUNT):
            thread = threading.Thread(target=self.worker, args=[])
            thread.start()
            self.threads.append(thread)

        self.sched_threads = []
        for i in range(SCHED_WORKER_COUNT):
            thread = threading.Thread(target=self.sched_worker, args=[])
            thread.start()
            self.sched_threads.append(thread)

        signal.signal(signal.SIGINT, self._handle_terminate)
        signal.signal(signal.SIGTERM, self._handle_terminate)

        ioloop.IOLoop.instance().start()

        LOG.info('Exited RUN')

    def _handle_terminate(self, *args):
        LOG.info("Received terminate signal")

        self.publisher.stop()
        self.stopping.set()

        for thread in self.threads:
            thread.join()
        for sched_thread in self.sched_threads:
            sched_thread.join()
        LOG.info('Threads exited')

        self._terminate()

        ioloop.IOLoop.instance().stop()

        LOG.info('Exiting terminate')

    def _terminate(self):
        LOG.info('Stopping Server daemon')

        # Destroy managed plugins
        for plugin_base in PLUGIN_BASES:
            for plugin in plugin_base.__subclasses__():
                if issubclass(plugin, ManagedPlugin):
                    try:
                        plugin().stop()
                    except:
                        pass

        self.notification_service.close()
        self.transport.shutdown()
        self.context.term()
        LOG.info('Stopped Server daemon')


def main():
    Dispatcher().choose()

if __name__ == '__main__':
    main()
