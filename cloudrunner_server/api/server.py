#!/usr/bin/python
# -*- coding: utf-8 -*-
# vim: tabstop=4 shiftwidth=4 softtabstop=4

# /*******************************************************
#  * Copyright (C) 2013-2014 CloudRunner.io <info@cloudrunner.io>
#  *
#  * Proprietary and confidential
#  * This file is part of CloudRunner Dashboard.
#  *
#  * CloudRunner Server can not be copied and/or distributed
#  * without the express permission of CloudRunner.io
#  *******************************************************/

import logging
import os
from pecan import request
from pecan.core import abort
import zmq

from cloudrunner import VAR_DIR
from cloudrunner import CONFIG_LOCATION
from cloudrunner.util.config import Config
from cloudrunner.core.message import M, Dispatch, GetNodes
from cloudrunner.util.logconfig import configure_loggers

configure_loggers(logging.DEBUG, os.path.join(VAR_DIR,
                                              'log',
                                              'cr-rest-api.log'))
LOG = logging.getLogger()

CONFIG = Config(CONFIG_LOCATION)
CONTEXT = None


class Master(object):

    def __init__(self, user, timeout=2):
        self.timeout = timeout
        self.proxy_uri = CONFIG.listen_uri or 'tcp://0.0.0.0:5559'
        if not self.proxy_uri.startswith('tcp://'):
            self.proxy_uri = 'tcp://' + self.proxy_uri
        self.user = user

    def close(self):
        # cleaning up
        # self.socket.close()
        pass

    def command(self, cmd, **kwargs):
        global CONTEXT
        if not CONTEXT:
            CONTEXT = zmq.Context(1)
        socket = CONTEXT.socket(zmq.DEALER)
        socket.connect(self.proxy_uri)
        kwargs["user"] = kwargs.pop('auth_user', self.user)
        # kwargs["roles"] = # {'org': 'DEFAULT', 'roles': {'*': '@'}}

        if cmd == 'dispatch':
            _req = Dispatch(**kwargs)
        elif cmd == "list_active_nodes":
            _req = GetNodes(org=request.user.org)

        def send(req):
            LOG.debug("SEND %r" % _req._)
            try:
                socket.send(req._)
                if not socket.poll(self.timeout * 1000):
                    LOG.warning("Timeout of %s sec expired" % self.timeout)
                    return None
                if socket.poll(1000):
                    ret = socket.recv()
                else:
                    ret = None
                LOG.debug("RECV %s" % str(ret))
                return ret
            except Exception, ex:
                return False, "Cannot connect to Master %r" % ex

        ret = send(_req)
        if not ret:
            return {}
        try:
            return M.build(ret)
        except Exception, ex:
            LOG.error(ret)
            LOG.exception(ex)
            if ret == "NOT AUTHORIZED":
                abort(403)
            return {}
        finally:
            socket.close()
