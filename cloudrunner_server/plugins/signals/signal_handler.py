#!/usr/bin/python
# -*- coding: utf-8 -*-
# vim: tabstop=4 shiftwidth=4 softtabstop=4

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

import json
import logging
import os
import zmq

from cloudrunner import LIB_DIR
from cloudrunner.core.message import AgentReq
from cloudrunner_server.plugins.args_provider import ArgsProvider
from cloudrunner_server.plugins.args_provider import CliArgsProvider
from cloudrunner_server.plugins.args_provider import ManagedPlugin
from cloudrunner_server.plugins.jobs.base import JobInOutProcessorPluginBase

from cloudrunner.util.http import load_from_link
from cloudrunner.util.http import parse_url

LOG = logging.getLogger(__name__)

try:
    import redis
    red = redis.StrictRedis(host='localhost', port=6379, db=0)
except:
    LOG.error("Redis is not installed, SignalHandler plugin will not work!")


class SignalHandlerPlugin(JobInOutProcessorPluginBase,
                          ArgsProvider, CliArgsProvider, ManagedPlugin):

    def __init__(self):
        self.db_dir = getattr(SignalHandlerPlugin, 'log_dir',
                              self._default_dir)

    @property
    def _default_dir(self):
        _def_dir = os.path.join(LIB_DIR, "cloudrunner",
                                "plugins", "signal_handler")
        if not os.path.exists(_def_dir):
            os.makedirs(_def_dir)
        return _def_dir

    @classmethod
    def start(cls):
        LOG.info("Starting Signal Handler")
        cls.context = zmq.Context()
        cls.push_sock = cls.context.socket(zmq.DEALER)
        cls.push_sock.connect(getattr(SignalHandlerPlugin,
                                      'server_uri',
                                      'tcp://0.0.0.0:38123'))

    @classmethod
    def stop(cls):
        LOG.info("Stopping Signal Handler")
        cls.push_sock.close(1)
        cls.context.term()

    def append_args(self):
        return [dict(arg='--attach_to', dest='attach')]

    def before(self, user_org, session_id, script, env, args, ctx, **kwargs):
        return (script, env)
        if args.attach_to:
            # Attach script source to signal
            self._attach(user_org, args.attach_to, script, False)
        return (script, env)

    def after(self, user_org, session_id, job_id, env, response, args, ctx,
              **kwargs):
        handlers = {}
        signal_items = [(k, v) for k, v in env.items()
                        if k.startswith("CRNSIGNAL")]
        for k, v in signal_items:
            if isinstance(v, list):
                signals = set(v)
            else:
                signals = set([v])
            env.pop(k)
            for sig in signals:
                key = '%s__%s' % (user_org[1], sig)
                handlers[sig] = red.smembers(key)
        for sig, handlers in handlers.items():
            for handler in set(handlers):
                meta = red.hgetall(handler + '__meta')
                if meta:
                    meta['signal'] = sig
                    LOG.info("Triggering target %(target)s "
                             "from signal %(signal)s for user %(user)s" %
                             (meta))

                    req = self._request(meta['user'], 'pwd123')
                    req.append(control='dispatch')
                    script_name = None
                    if meta['is_link']:
                        # TODO: Load from http(s)
                        url = meta['target']
                        proto_tokens = parse_url(url)
                        script_name = url.rpartition('/')[2]

                        if not proto_tokens:
                            LOG.error("%s doesn't seem to be a valId URL, "
                                      "skipping processing" % url)
                            continue
                        auth_kwargs = {}
                        if meta['auth']:
                            auth_kwargs['auth_user'] = meta['user']
                            auth_kwargs['auth_token'] = ctx.create_auth_token(
                                expiry=30)

                        status, script_content = load_from_link(
                            proto_tokens[0],
                            proto_tokens[1],
                            **auth_kwargs)
                        if status != 0:
                            LOG.error("Cannot load script from %s, "
                                      "skipping processing, error: [%s]" % (
                                          url, status))
                            continue

                        req.append(data=script_content)
                    else:
                        req.append(data=meta['target'])
                    req.append(env=env)
                    trigger_stack = kwargs.get('trigger', 0)
                    if not trigger_stack:
                        # First trigger
                        call_name = kwargs.get('caller', session_id)
                    else:
                        call_name = session_id
                    trigger_stack += 1  # Incr trigger stack

                    max_stack = kwargs.get('max_stack_depth', 5)
                    if trigger_stack > max_stack:
                        # Avoid recursive calls
                        LOG.warn("Max re-trigger stack reached, stopping")
                        continue
                    req.append(trigger=trigger_stack)
                    req.append(max_stack=max_stack)

                    if script_name:
                        script_name += ' '

                    if trigger_stack == 1:
                        req.append(caller="%s[%s] Triggered from %s" %
                                  (script_name, sig, call_name))
                    else:
                        req.append(caller="%s[%s] Re-triggered from %s" %
                                  (script_name, sig, call_name))
                    SignalHandlerPlugin.push_sock.send_multipart(req.pack())
        return True

    def _request(self, login, password):
        _req = AgentReq(login=login,
                        password=password)
        return _req

    def append_cli_args(self, arg_parser):
        sig_actions = arg_parser.add_subparsers(dest='action')

        attach = sig_actions.add_parser('attach', add_help=False,
                                        help='Attach target to signal')
        attach.add_argument('signal', help='Signal name')
        attach.add_argument('target', help='Target name')
        attach.add_argument('-a', '--auth', action='store_true',
                            help='Pass auth headers')

        detach = sig_actions.add_parser('detach',
                                        help='Detach target from signal')
        detach.add_argument('signal', help='Signal name')
        detach.add_argument('target', help='Target name')

        return "signal"

    def call(self, user_org, data, ctx, args):

        if args.action == 'attach':
            return self._attach(user_org, args.signal, args.target, args.auth)
        elif args.action == 'detach':
            return self._detach(user_org, args.signal, args.target)
        return False, "Unknown"

    def _attach(self, user, signal, target, use_auth):
        LOG.info("[%s] Attaching to %s, auth: %s" %
                (user[0], signal, use_auth))

        org = user[1]
        key = '__'.join([org, user[0], signal, target])

        # Ensure data is in lists
        is_link = bool(parse_url(target))
        new_hndl = red.sadd('signals', key)
        red.hmset(key + '__meta', dict(user=user[0],
                                       target=target,
                                       auth=use_auth,
                                       is_link=is_link))

        if new_hndl:
            red.sadd('%s__%s' % (org, signal), key)
            return True, 'Added'
        else:
            return True, "Signal handler exists, but will be updated"

    def _detach(self, user, signal, target):
        LOG.info("[%s] Detaching %s from %s" % (user[0], target, signal))
        org = user[1]
        key = '__'.join([org, user[0], signal, target])
        red.srem('%s__%s' % (org, signal), key)
        red.srem('signals', key)
        red.hdel(key + '__meta', 'user', 'target', 'auth', 'is_link')
        return True, 'Detached'
