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

import logging
import signal
import sys
from threading import Thread

from cloudrunner.core.exceptions import ConnectionError
from cloudrunner.core.message import (ADMIN_TOWER, ControlReq, StatusCodes)
from cloudrunner.util.shell import Timer

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
                packet = self.admin_endp.recv(100)
                if packet:
                    req = ControlReq.build(*packet)
                    if not req:
                        LOG.warn("ADMIN_TOWER invalid packet recv: %s" %
                                 packet)
                        continue
                    LOG.info("ADMIN_TOWER recv: %s" % req)
                    rep = self.process(req)
                    if not rep:
                        continue
                    LOG.info("ADMIN_TOWER reply: %s: %s" %
                             (req.ident, rep[:2]))
                    packets.append([req.ident, req.node] + rep)
                while packets:
                    packet = packets.pop(0)
                    self.node_reply_queue.send(*packet)
            except ConnectionError:
                break
            except KeyboardInterrupt:
                break
            except Exception, ex:
                LOG.exception(ex)

        self.close()

    def process(self, rq):
        LOG.info("Received admin req: %s %s" % (rq.control, rq.node))

        if rq.control == 'ECHO':
            return [rq.node, rq.data or 'ECHO']
        try:
            if rq.control == 'REGISTER':
                try:
                    success, approval = self.backend.verify_node_request(
                        rq.node,
                        rq.data)
                    if success:
                        return [rq.node, 'APPROVED', approval]
                    else:
                        return [rq.node, 'REJECTED', approval]
                except Exception, ex:
                    LOG.exception(ex)
                    return [rq.node, 'REJECTED', "APPR_FAIL"]

            return [rq.node, 'UNKNOWN']
        except Exception, ex:
            LOG.exception(ex)
            return ['', 'UNKNOWN']

        return ['', 'UNKNOWN']

    def close(self, *args):
        LOG.info("Stopping Admin Process")
        self.admin_endp.close()
        self.node_reply_queue.close()
        LOG.info("Stopped admin Process")
