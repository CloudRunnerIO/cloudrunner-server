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

try:
    import argcomplete
except ImportError:
    pass
import argparse
import json
import logging
import os
import signal
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
from cloudrunner_server.plugins.args_provider import ManagedPlugin
from cloudrunner_server.plugins.auth.base import AuthPluginBase
from cloudrunner_server.plugins.logs.base import LoggerPluginBase
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

        arg_parser.add_argument('-p', '--pidfile', dest='pidfile',
                                help='Daemonize process with the '
                                'given pid file')
        arg_parser.add_argument('-c', '--config', help='Config file')
        arg_parser.add_argument(
            'action',
            choices=[
                'start', 'stop', 'restart', 'run'],
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
        self.scheduler_uri = SCHEDULER_URI

        # instantiate dispatcher implementation
        self.transport_class = local_plugin_loader(CONFIG.transport)
        if not self.transport_class:
            LOG.fatal('Cannot find transport class. Set it in config file.')
            exit(1)

        self.loaded_plugins = load_plugins(CONFIG, bases=PLUGIN_BASES)
        args_plugins = argparse.ArgumentParser(add_help=False)
        args_plugins.add_argument('-t', '--timeout', help="Timeout")

        self.plugin_register = {}
        for plugin_classes in self.loaded_plugins.values():
            for plugin in plugin_classes:
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
                        plugin.start(CONFIG)
                    except Exception, ex:
                        LOG.error('Plugin error(%s):  %r' % (plugin, ex))

        self.scheduler_class = None
        if CONFIG.scheduler:
            self.scheduler_class = local_plugin_loader(CONFIG.scheduler)
            LOG.info('Loaded scheduler class: %s' %
                     self.scheduler_class.__name__)
        else:
            LOG.warn('Cannot find scheduler class. Set it in config file.')

        if AuthPluginBase.__subclasses__():
            self.auth_klass = AuthPluginBase.__subclasses__()[0]
        else:
            if not CONFIG.auth:
                LOG.warn('No Auth plugin found')
            else:
                self.auth_klass = local_plugin_loader(CONFIG.auth)

        self.logger_klass = None
        if LoggerPluginBase.__subclasses__():
            self.logger_klass = LoggerPluginBase.__subclasses__()[0]
        else:
            if not CONFIG.logger:
                LOG.warn('No Logger plugin found')
            else:
                self.logger_klass = local_plugin_loader(CONFIG.logger)

        self.config = CONFIG
        self.auth = self.auth_klass(self.config)
        self.auth.set_context_from_config()
        LOG.info("Using %s.%s for Auth backend" % (
            self.auth_klass.__module__,
            self.auth_klass.__name__))

        self.logger = None
        if self.logger_klass:
            self.logger = self.logger_klass(self.config)
            self.logger.set_context_from_config()
            LOG.info("Using %s.%s for Logger backend" % (
                self.logger_klass.__module__,
                self.logger_klass.__name__))

        self.plugin_context = PluginContext(self.auth)

        self.plugin_context.args_plugins = args_plugins
        if JobInOutProcessorPluginBase.__subclasses__():
            job_plugins = JobInOutProcessorPluginBase.__subclasses__()
            LOG.info('Loading Job Processing plugins: %s' %
                     ', '.join([pl.__name__ for pl in job_plugins]))
        else:
            job_plugins = []
        self.plugin_context.job_plugins = job_plugins

        if IncludeLibPluginBase.__subclasses__():
            lib_plugins = IncludeLibPluginBase.__subclasses__()
            LOG.info('Loading Lib Save plugins: %s' %
                     ', '.join([pl.__name__ for pl in lib_plugins]))
        else:
            lib_plugins = []
        self.plugin_context.lib_plugins = lib_plugins

    def _login(self, auth_type=1):
        self.auth_type = auth_type
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
        if self.auth_type == 2:
            is_token = True
        else:
            is_token = False
        (user, token, org) = self.auth.create_token(self.user_id,
                                                    self.user_token,
                                                    is_token=is_token,
                                                    **kwargs)
        if token:
            return ["TOKEN", token, org]
        else:
            return ["FAILURE"]

    def unset_api_token(self, *args, **kwargs):
        if self.auth_type != 2:
            return [False, "NO TOKEN PASSED"]

        return self.auth.delete_token(self.user_id, self.user_token)

    def plugins(self, payload, remote_user_map, **kwargs):
        plug = [(args, [c.__module__ for c in p])
                for (args, p) in sorted(self.plugin_register.items(),
                                        key=lambda x: (x[1], x[0]))]

        return [plug]

    def __plugin(self, payload, remote_user_map, **kwargs):
        resp = []
        plugin_name = kwargs.pop('plugin')
        plugin_action = kwargs.pop('action')
        plugin_return_type = kwargs.get('return_type')
        plugin = self.plugin_cli_register.get(plugin_name)
        if not plugin:
            return [(False, 'Plugin %s not found' % plugin_name)]

        user_org = (self.user_id, remote_user_map.org)
        try:
            args = None
            try:
                args = plugin.parse(plugin_action, plugin_return_type,
                                    **kwargs.get('args', {}))
            except Exception, ex:
                LOG.error('%r' % ex)
                resp.append((False, str(ex)))
            if args:
                ret = plugin.plugin.call(
                    user_org,
                    self.plugin_context.instance(
                        self.user_id, self.user_token,
                        auth_type=self.auth_type),
                    args)
                if ret:
                    resp.append(ret)
        except ValueError, verr:
            resp.append((False, str(verr)))
        except Exception, ex:
            LOG.exception(ex)
            resp.append((False, plugin.help()))

        return resp

    def list_nodes(self, payload, remote_user_map, **kwargs):
        cert = CertController(CONFIG)
        org = remote_user_map.org if self.config.security.use_org else None
        nodes = cert.get_approved_nodes(org)
        all_nodes = self.list_active_nodes(payload, remote_user_map,
                                           **kwargs)[1]
        active_nodes = [a[0] for a in all_nodes]
        for node in nodes:
            if node not in active_nodes:
                all_nodes.append((node, None))
        return (True, all_nodes)

    def list_pending_nodes(self, payload, remote_user_map, **kwargs):
        cert = CertController(CONFIG)
        org = remote_user_map.org if self.config.security.use_org else None
        nodes = cert.list_pending(org)
        return (True, [node[0] for node in nodes])

    def list_active_nodes(self, payload, remote_user_map, **kwargs):
        if hasattr(self, 'backend'):
            tenant = self.backend.tenants.get(remote_user_map.org, [])
            nodes = []
            if tenant:
                nodes = [(n.name, int(n.last_seen))
                         for n in tenant.active_nodes()]
            return (True, nodes)
        return (True, [])

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

        session_id = uuid.uuid4().hex
        promise = self.manager.prepare_session(
            self.user_id, session_id, payload, remote_user_map,
            self.plugin_context.instance(self.user_id, self.user_token,
                                         auth_type=self.auth_type),
            **kwargs)
        promise.main = True
        return promise

    def worker(self, *args):
        job_queue = self.backend.consume_queue('requests')

        while not self.stopping.is_set():
            try:
                frames = None
                try:
                    raw_frames = job_queue.recv(timeout=500)
                    if not raw_frames:
                        continue
                except ConnectionError:
                    break
                except Exception, ex:
                    LOG.exception(ex)
                    if not self.stopping.is_set():
                        continue
                # User -> queue
                sender = ''
                ident = raw_frames.pop(0)
                data = json.loads(raw_frames[0])
                if data[0] == 'QUIT':
                    # Node exited
                    continue
                req = message.AgentReq.build(*data)
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
                            ["ERROR: [%s] command not available on Master"
                             % req.control]))
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
                    job_queue.send(ident, 'NOT AUTHORIZED')
                    continue

                remote_user_map = auth_check[1]
                LOG.info('action: %s, user: %s/%s' % (req.control,
                                                      req.login,
                                                      remote_user_map.org))
                response = getattr(self, req.control)(req.data,
                                                      remote_user_map,
                                                      **req.kwargs)
                if isinstance(response, Promise):
                    # Return job id
                    job_queue.send(
                        ident,
                        json.dumps([True, response.session_id]))
                    response.proxy = sender
                    response.peer = ident
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
                    data = [StatusCodes.FINISHED, list(response)]
                    job_queue.send(ident, json.dumps(data))
            except ConnectionError:
                break

        job_queue.close()

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
                    response.proxy = ''
                    response.peer = ''
                    response.resolve()

            except ConnectionError:
                break
            except Exception, err:
                LOG.exception(err)
                continue

        task_queue.close()
        LOG.info('Scheduler worker exited')

    def logger_worker(self, *args):
        log_queue = self.backend.consume_queue('logger')

        while not self.stopping.is_set():
            try:
                frames = log_queue.recv(timeout=500)
                if not frames:
                    continue
                try:
                    self.logger.log(**json.loads(frames[0]))
                except Exception, err:
                    LOG.exception(err)
            except ConnectionError:
                break
            except Exception, err:
                LOG.exception(err)
                continue

        log_queue.close()
        LOG.info('Logger worker exited')

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
        LOG_WORKER_COUNT = int(CONFIG.log_worker_count or 3)

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

        self.logger_threads = []
        if self.logger:
            for i in range(LOG_WORKER_COUNT):
                thread = threading.Thread(target=self.logger_worker, args=[])
                thread.start()
                self.logger_threads.append(thread)

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
        for logger_thread in self.logger_threads:
            logger_thread.join()

        LOG.info('Threads exited')

        # Destroy managed plugins
        for plugin_base in PLUGIN_BASES:
            for plugin in plugin_base.__subclasses__():
                if issubclass(plugin, ManagedPlugin):
                    try:
                        plugin.stop()
                    except:
                        pass

        LOG.info('Stopped Server daemon')


def main():
    Dispatcher().choose()

if __name__ == '__main__':
    main()
