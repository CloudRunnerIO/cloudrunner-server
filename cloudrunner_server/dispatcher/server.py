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

from cloudrunner import CONFIG_LOCATION
from cloudrunner import LOG_LOCATION
from cloudrunner.util.config import Config
from cloudrunner.util.logconfig import configure_loggers

CONFIG = Config(CONFIG_LOCATION)

if CONFIG.verbose_level:
    configure_loggers(getattr(logging, CONFIG.verbose_level, 'INFO'),
                      LOG_LOCATION)
else:
    configure_loggers(logging.DEBUG if CONFIG.verbose else logging.INFO,
                      LOG_LOCATION)

from cloudrunner.core.exceptions import ConnectionError
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
from cloudrunner_server.dispatcher.manager import SessionManager
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
                                      CONFIG.listen_uri or '0.0.0.0:5559'])
        self.scheduler_uri = SCHEDULER_URI

        # instantiate dispatcher implementation
        self.transport_class = local_plugin_loader(CONFIG.transport)
        if not self.transport_class:
            LOG.fatal('Cannot find transport class. Set it in config file.')
            exit(1)

        load_plugins(CONFIG)

        args_plugins = argparse.ArgumentParser(add_help=False)
        args_plugins.add_argument('-t', '--timeout', help="Timeout")

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

                if issubclass(plugin, ManagedPlugin):
                    try:
                        plugin().start()
                    except Exception, ex:
                        LOG.error('Plugin error(%s):  %r' % (plugin, ex))

        for plugin in CliArgsProvider.__subclasses__():
            try:
                # overwrite error method
                def _toString(parser):
                    from StringIO import StringIO
                    buf = StringIO()
                    parser.print_help(file=buf)
                    return buf.getvalue()

                def _error(cls, *arg, **kw):
                    raise ValueError(cls._toString())
                argparse.ArgumentParser._toString = _toString
                argparse.ArgumentParser.error = _error
                plugin_plugins = argparse.ArgumentParser(
                    add_help=False,
                    prog='')
                plugin.parser = plugin_plugins
                arg = plugin().append_cli_args(plugin_plugins)
                if not arg:
                    LOG.warn("Plugin %s doesn't return correct id" %
                             plugin.__name__)
                    continue
                if arg in self.plugin_cli_register:
                    LOG.warn(
                        "Duplicate plugin name %s from plugin [%s]" %
                        (arg, plugin.__name__))
                    continue
                self.plugin_cli_register[arg] = plugin
            except Exception, ex:
                LOG.exception(ex)
                continue

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
        LOG.info("Using %s.%s for Auth backend" % (
            self.auth_klass.__module__,
            self.auth_klass.__name__))

        self.plugin_context = PluginContext(self.auth)

        self.plugin_context.args_plugins = args_plugins
        if JobInOutProcessorPluginBase.__subclasses__():
            job_plugins = JobInOutProcessorPluginBase.__subclasses__()
            LOG.info('Loading Job Processing plugins: %s' % job_plugins)
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
        return (True, remote_user_map.org)  # Already logged, return org

    def get_api_token(self, *args, **kwargs):
        (user, token, org) = self.auth.create_token(self.user_id,
                                                    self.user_token, **kwargs)
        if token:
            return ["TOKEN", token, org]
        else:
            return ["FAILURE"]

    def plugins(self, payload, remote_user_map, **kwargs):
        plug = [(args, [c.__module__ for c in p])
                for (args, p) in sorted(self.plugin_register.items(),
                                        key=lambda x: (x[1], x[0]))]

        cli_plug = [(plugin, p.__module__) for (plugin, p) in
                    self.plugin_cli_register.items()]

        return [plug, cli_plug]

    def plugin(self, payload, remote_user_map, **kwargs):
        resp = []
        plugin_name = kwargs.pop('plugin')
        data = kwargs.pop('data', None)
        plugin = self.plugin_cli_register.get(plugin_name)
        if not plugin:
            return [(False, 'Plugin %s not found' % plugin_name)]

        user_org = (self.user_id, remote_user_map.org)

        try:
            args = kwargs.get('args', '').split()
            if '--jhelp' in args:

                args.remove('--jhelp')

                p = plugin.parser
                while args and p._subparsers:
                    posit = args.pop(0)
                    # is subparser?
                    for act in p._subparsers._actions:
                        if isinstance(act, argparse._SubParsersAction):
                            if posit in act.choices:
                                p = act.choices[posit]
                    if not args:
                        break
                    posit = args.pop(0)
                # Print formated help

                arguments = []
                for action in p._actions:
                    if isinstance(action, argparse._SubParsersAction):
                        arguments.append({action.dest: action.choices.keys()})
                    elif isinstance(action, argparse._StoreAction):
                        arguments.extend(action.option_strings)
                    elif isinstance(action, argparse._StoreTrueAction):
                        arguments.append('@' + action.dest)
                    else:
                        arguments.append(action.dest)
                return [(True, arguments)]
            else:
                ns, _ = plugin.parser.parse_known_args(args)
                ret = plugin().call(user_org, payload,
                                    self.plugin_context.instance(
                                    self.user_id, self.user_token),
                                    ns)
                if ret:
                    resp.append(ret)
        except ValueError, verr:
            resp.append((False, str(verr)))
        except Exception, ex:
            LOG.exception(ex)
            resp.append((False, plugin.parser._toString()))

        return resp

    def list_nodes(self, payload, remote_user_map, **kwargs):
        cert = CertController(CONFIG)
        org = remote_user_map.org if self.config.security.use_org else None
        nodes = cert.get_approved_nodes(org)
        return (True, [node for node in nodes])

    def list_pending_nodes(self, payload, remote_user_map, **kwargs):
        cert = CertController(CONFIG)
        org = remote_user_map.org if self.config.security.use_org else None
        nodes = cert.list_pending(org)
        return (True, [node[0] for node in nodes])

    def list_active_nodes(self, payload, remote_user_map, **kwargs):
        tenant = self.backend.tenants.get(remote_user_map.org, [])
        nodes = []
        if tenant:
            nodes = [n.name for n in tenant.active_nodes()]
        return (True, nodes)

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
        session = [sess for sess in self.manager.subscriptions.get(
            session_id, []) if sess.owner == self.user_id]
        if not session:
            return [False, "You are not the owner of the session"]
        job_queue = self.manager.backend.publish_queue('user_input')
        job_queue.send(job_id, '', 'INPUT', session_id, self.user_id,
                       str(remote_user_map.org), payload, targets)

        return [True, "Notified"]

    def term(self, payload, remote_user_map, **kwargs):
        session_id = str(kwargs.pop('session_id'))

        session_sub = [sess for sess in self.manager.subscriptions.get(
            session_id, []) if sess.owner == self.user_id]
        if not session_sub:
            return [False, "You are not the owner of the session"]

        session = self.manager.sessions.get(session_id)
        if session:
            session.stop_reason = str(kwargs.get('action', 'term'))
            session.session_event.set()
            return [True, "Session terminated"]
        else:
            return [False, "Session not found"]

    def dispatch(self, payload, remote_user_map, **kwargs):
        """
        Dispatch script to targeted nodes
        """

        session_id = str(uuid.uuid1())

        promise = self.manager.prepare_session(
            self.user_id, session_id, payload, remote_user_map,
            self.plugin_context.instance(self.user_id, self.user_token),
            **kwargs)
        promise.main = True
        return promise

    def worker(self, *args):
        job_queue = self.backend.consume_queue('requests')
        job_done_queue = self.backend.consume_queue('finished_jobs')
        log_queue = self.backend.create_fanout('logger')

        poller = self.backend.create_poller(job_queue, job_done_queue)

        while not self.stopping.is_set():
            ready = {}
            try:
                frames = None
                try:
                    ready = poller.poll(300)
                    if not ready:
                        continue
                except ConnectionError:
                    break
                except Exception, ex:
                    LOG.exception(ex)
                    if not self.stopping.is_set():
                        continue
                if job_queue in ready:
                    # User -> queue
                    frames = job_queue.recv()
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
                        job_queue.send(
                            sender, StatusCodes.FINISHED,
                            json.dumps(
                                ["ERROR: [%s] command not available on Master" %
                                 req.control]))
                        continue

                    self.user_id = req.login
                    if req.auth_type == 1:
                        # Password auth
                        self.user_token = req.password
                    else:
                        # Token auth
                        self.user_token = req.password

                    auth_check = self._login(req.auth_type)
                    if not auth_check[0]:
                        job_queue.send(sender, 'NOT AUTHORIZED')
                        continue

                    remote_user_map = auth_check[1]
                    LOG.info('action: %s, user: %s/%s' % (req.control,
                                                          req.login,
                                                          remote_user_map.org))
                    # def pipe_callback(*args):
                    #    self.job_queue.send_multipart(
                    #        sender, StatusCodes.PIPEOUT,
                    #         json.dumps(args))

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
                                for sub in self.manager.subscriptions[
                                    response.session_id]:
                                    if sub.session_id == response.session_id:
                                        self.manager.subscriptions[
                                            response.session_id].remove(sub)
                                        break
                            except:
                                pass
                        else:
                            self.manager.subscriptions[
                                response.session_id].append(response)
                    elif response:
                        job_queue.send(sender, StatusCodes.FINISHED,
                                       json.dumps(response))

                elif job_done_queue in ready:
                    # Done -> user
                    frames = job_done_queue.recv()
                    job_queue.send(*frames)
                    log_queue.send(*frames[1:])
            except ConnectionError:
                break

        job_queue.close()
        job_done_queue.close()
        log_queue.close()

        LOG.info('Server worker exited')

    def sched_worker(self, *args):
        task_queue = self.backend.consume_queue('scheduler')

        while not self.stopping.is_set():
            try:
                try:
                    frames = task_queue.recv(500)
                    if not frames:
                        continue
                except ConnectionError:
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

            except ConnectionError:
                break
            except Exception, err:
                LOG.exception(err)
                continue

        task_queue.close()
        LOG.info('Scheduler worker exited')

    def choose(self):
        getattr(self, self.args.action)()

    def run(self):

        self.init_libs()

        if not self.config.sock_dir:
            raise Exception("Socket dir (sock_dir) is not set in config")
        if not os.path.exists(self.config.sock_dir):
            try:
                os.makedirs(self.config.sock_dir)
            except:
                raise Exception("Socket dir doesn't exist and "
                                "cannot be created")

        WORKER_COUNT = int(CONFIG.workers_count or 10)
        SCHED_WORKER_COUNT = int(CONFIG.sched_worker_count or 3)

        self.stopping = threading.Event()

        self.backend = self.transport_class(self.config)
        self.backend.prepare()

        self.admin = Admin(self.config, self.backend)
        self.admin.start()

        self.manager = SessionManager(self.config, self.backend)
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

        self.backend.loop()

        LOG.info('Exited main thread')

    def _handle_terminate(self, *args):
        LOG.info("Received terminate signal")
        self.backend.terminate()
        self.manager.stop()
        self.stopping.set()

        for thread in self.threads:
            thread.join()
        for sched_thread in self.sched_threads:
            sched_thread.join()
        LOG.info('Threads exited')

        # Destroy managed plugins
        for plugin_base in PLUGIN_BASES:
            for plugin in plugin_base.__subclasses__():
                if issubclass(plugin, ManagedPlugin):
                    try:
                        plugin().stop()
                    except:
                        pass

        LOG.info('Stopped Server daemon')


def main():
    Dispatcher().choose()

if __name__ == '__main__':
    main()
