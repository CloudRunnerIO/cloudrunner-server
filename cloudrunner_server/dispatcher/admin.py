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
from threading import Thread

from cloudrunner.core.exceptions import ConnectionError
from cloudrunner.core.message import (ADMIN_TOWER, Control, Register)

LOG = logging.getLogger('Control Tower')


class Admin(Thread):

    """
    Admin class to process control requests like Register, etc.
    """

    def __init__(self, config, backend):
        super(Admin, self).__init__()
        self.config = config
        self.backend = backend

    def run(self):
        # Endpoint to receive commands from nodes
        self.admin_endp = self.backend.consume_queue('in_messages',
                                                     ident=ADMIN_TOWER)
        self.node_reply_queue = self.backend.publish_queue('out_messages')

        packets = []
        while True:
            try:
                packed = self.admin_endp.recv(100)
                if packed:
                    req = Control.build(packed[0])
                    if not req:
                        LOG.warn("ADMIN_TOWER invalid packet recv: %s" %
                                 packed)
                        continue
                    LOG.info("ADMIN_TOWER recv: %s" % req)
                    rep = self.process(req)
                    if not rep:
                        continue
                    LOG.info("ADMIN_TOWER reply: %s" % rep)
                    rep.hdr.ident = req.hdr.ident
                    packets.append(rep)
                while packets:
                    msg = packets.pop(0)
                    self.node_reply_queue.send(msg._)
            except ConnectionError:
                break
            except KeyboardInterrupt:
                break
            except Exception, ex:
                LOG.exception(ex)

        self.close()
        LOG.info("Exiting Admin thread")

    def process(self, req):
        LOG.info("Received admin req: %s %s" % (req.control, req.node))

        if req.action == 'ECHO':
            return [req.node, req.data or 'ECHO']
        if req.action == 'REGISTER':
            try:
                success, approval = self.backend.verify_node_request(
                    req.node,
                    req.data)
                if success:
                    return Register(req.node, 'APPROVED', approval)
                else:
                    return Register(req.node, 'REJECTED', approval)
            except Exception, ex:
                LOG.exception(ex)
                return Register(req.node, 'REJECTED', 'APPR_FAIL')

        return None

    def close(self, *args):
        LOG.info("Stopping Admin Process")
        self.admin_endp.close()
        self.node_reply_queue.close()
        LOG.info("Stopped admin Process")
