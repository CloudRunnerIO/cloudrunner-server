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

import json
import logging
import os
from pecan import conf
from pecan.core import abort
import zmq

import cloudrunner
from cloudrunner.core import message
from cloudrunner.util.logconfig import configure_loggers

configure_loggers(logging.DEBUG,
                  os.path.join(cloudrunner.VAR_DIR, 'log', 'cr-rest-api.log'))
LOG = logging.getLogger()


CONTEXT = None


class Master(object):

    def __init__(self, user, token, timeout=2):
        self.timeout = timeout
        self.proxy_uri = conf.zmq['server_uri']
        self.user = user
        self.token = token

    def close(self):
        # cleaning up
        # self.socket.close()
        pass

    def command(self, cmd, auth_type=2, **kwargs):
        global CONTEXT
        if not CONTEXT:
            CONTEXT = zmq.Context(1)
        socket = CONTEXT.socket(zmq.DEALER)
        socket.connect(self.proxy_uri)
        _req = message.AgentReq(login=kwargs.get("auth_user", self.user),
                                auth_type=auth_type,
                                password=kwargs.get("auth_token", self.token),
                                control=cmd)
        _req.append(**kwargs)

        LOG.info("SEND %s" % _req)

        def send(req):
            LOG.info(req.pack())
            try:
                socket.send_multipart([json.dumps(req.pack(extra=True))])
                if not socket.poll(self.timeout * 1000):
                    LOG.warning("Timeout of %s sec expired" % self.timeout)
                    return None
                if socket.poll(1000):
                    ret = socket.recv_multipart()
                else:
                    ret = None
                LOG.info("RECV %s" % str(ret))
                return ret
            except Exception, ex:
                return False, "Cannot connect to Master %r" % ex

        ret = send(_req)
        if not ret:
            return {}
        try:
            return json.loads(ret[0])[1]
        except Exception, ex:
            LOG.error(ret)
            LOG.exception(ex)
            if ret == "NOT AUTHORIZED":
                abort(403)
            return {}
        finally:
            socket.close()
