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
import os
import zmq

from cloudrunner import LIB_DIR
from cloudrunner_server.plugins.args_provider import ArgsProvider
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
                          ArgsProvider,
                          ManagedPlugin):

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
    def start(cls, config):
        LOG.info("Starting Signal Handler")
        cls.context = zmq.Context()
        cls.push_sock = cls.context.socket(zmq.DEALER)
        cls.push_sock.connect(getattr(SignalHandlerPlugin,
                                      'server_uri',
                                      'tcp://0.0.0.0:5559'))

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
            self.attach(user_org, args.attach_to, script, False)
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

                    token = ctx.create_auth_token(expiry=30)
                    req = self._request(meta['user'], token)
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
                            auth_kwargs['auth_token'] = token

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
                        req.append(caller="%s[%s] Triggered from %s" % (
                            script_name, sig, call_name))
                    else:
                        req.append(caller="%s[%s] Re-triggered from %s" % (
                            script_name, sig, call_name))
                    SignalHandlerPlugin.push_sock.send_multipart(req.pack())
        return True

    def list(self, user_org):
        triggers = red.smembers('signals')

        coll = []
        for trig in triggers:
            if not trig.startswith('%s__' % user_org[1]):
                continue
            meta = red.hgetall(trig + '__meta')
            sig = trig.split('__')[2]
            meta['signal'] = sig
            meta['is_link'] = meta['is_link'] == 'True'
            meta['auth'] = meta['auth'] == 'True'
            coll.append(meta)

        return True, coll

    def attach(self, user, signal, target, use_auth):
        LOG.info("[%s] Attaching to %s, auth: %s" % (
            user[0], signal, use_auth))

        org = user[1]
        key = '__'.join([org, user[0], signal, target])

        # Ensure data is in lists
        is_link = bool(parse_url(target))
        new_hndl = red.sadd('signals', key)
        red.hmset(key + '__meta', dict(user=user[0],
                                       target=target,
                                       auth=bool(use_auth),
                                       is_link=is_link))

        if new_hndl:
            red.sadd('%s__%s' % (org, signal), key)
            return True, 'Added'
        else:
            return True, "Signal handler exists, but will be updated"

    def detach(self, user, signal, target):
        LOG.info("[%s] Detaching %s from %s" % (user[0], target, signal))
        org = user[1]
        key = '__'.join([org, user[0], signal, target])
        is_rem = red.srem('signals', key)
        red.srem('%s__%s' % (org, signal), key)
        red.hdel(key + '__meta', 'user', 'target', 'auth', 'is_link')
        if is_rem:
            return True, 'Detached'
        else:
            return False, 'Signal not detached'
