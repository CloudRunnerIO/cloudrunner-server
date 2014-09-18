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
import logging
import os
import signal
import threading

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
from cloudrunner.core.message import (M, Dispatch, GetNodes, Nodes,
                                      Error, Queued)
from cloudrunner.util.daemon import Daemon
from cloudrunner.util.loader import load_plugins, local_plugin_loader
from cloudrunner.util.shell import colors

from cloudrunner_server.dispatcher import (TaskQueue)
from cloudrunner_server.dispatcher.admin import Admin
from cloudrunner_server.dispatcher.manager import SessionManager
from cloudrunner_server.plugins import PLUGIN_BASES
from cloudrunner_server.plugins.args_provider import (ArgsProvider,
                                                      ManagedPlugin)
from cloudrunner_server.plugins.logs.base import LoggerPluginBase

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

        self.logger_klass = None
        if LoggerPluginBase.__subclasses__():
            self.logger_klass = LoggerPluginBase.__subclasses__()[0]
        else:
            if not CONFIG.logger:
                LOG.warn('No Logger plugin found')
            else:
                self.logger_klass = local_plugin_loader(CONFIG.logger)

        self.config = CONFIG

        self.logger = None
        if self.logger_klass:
            self.logger = self.logger_klass(self.config)
            self.logger.set_context_from_config()
            LOG.info("Using %s.%s for Logger backend" % (
                self.logger_klass.__module__,
                self.logger_klass.__name__))

    def list_active_nodes(self, org):
        msg = Nodes()
        if hasattr(self, 'backend'):
            tenant = self.backend.tenants.get(org, None)
            if tenant:
                msg.nodes = [dict(name=n.name, last_seen=int(n.last_seen))
                             for n in tenant.active_nodes()]
            return msg
        return msg

    """
    def attach(self, payload, remote_user_map, **kwargs):
        '''
        Attach to an existing pre-defined session
        or create it if not started yet
        '''
        (targets, req_args) = parser.parse_selectors(payload)
        queue = TaskQueue()
        queue.targets = targets
        return queue

    def detach(self, payload, remote_user_map, **kwargs):
        '''
        Detach from an existing pre-defined session
        '''
        queue = TaskQueue()
        queue.remove = True
        return queue
    """

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

    def dispatch(self, user, tasks, remote_user_map, env=None):
        """
        Dispatch script to targeted nodes
        """

        queue = self.manager.prepare_session(
            self.user_id, tasks, remote_user_map, env=env)
        return queue

    def worker(self, *args):
        job_queue = self.backend.consume_queue('requests')

        while not self.stopping.is_set():
            try:
                raw_frames = None
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
                pack = raw_frames.pop(0)
                msg = M.build(pack)

                if msg.control == 'QUIT':
                    # Node exited
                    continue
                if not msg:
                    LOG.error("Invalid request %s" % raw_frames)
                    continue

                if isinstance(msg, Dispatch):
                    self.user_id = msg.user

                    remote_user_map = msg.roles
                    LOG.info('user: %s/%s' % (msg.user,
                                              remote_user_map['org']))
                    response = self.dispatch(msg.user, msg.tasks, msg.roles,
                                             env=getattr(msg, 'env', {}))

                elif isinstance(msg, GetNodes):
                    response = self.list_active_nodes(msg.org)
                else:
                    # TODO: Check if a plugin supports command
                    job_queue.send(sender, Error(msg="Unknown command"))
                    continue

                if isinstance(response, TaskQueue):
                    # Return job id
                    job_queue.send([ident,
                                    Queued(task_ids=response.task_ids)._])
                    response.process()
                elif isinstance(response, M):
                    job_queue.send(ident, response._)
            except ConnectionError:
                break

        job_queue.close()

        LOG.info('Server worker exited')

    def logger_worker(self, *args):
        log_queue = self.backend.consume_queue('logger')

        while not self.stopping.is_set():
            try:
                frames = log_queue.recv(timeout=500)
                if not frames:
                    continue
                try:
                    self.logger.log(M.build(frames[0]))
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
