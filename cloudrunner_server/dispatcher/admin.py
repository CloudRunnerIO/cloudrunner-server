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
import M2Crypto as m
from os import path as p
from threading import Thread

from cloudrunner.core.exceptions import ConnectionError
from cloudrunner.core.message import (ADMIN_TOWER, ControlReq, StatusCodes,
                                      is_valid_host, TOKEN_SEPARATOR)
from cloudrunner_server.master.functions import CertController

LOG = logging.getLogger('Control Tower')


class Admin(Thread):

    """
    Admin class to process control requests like Register, etc.
    """

    def __init__(self, config, backend):
        super(Admin, self).__init__()
        self.config = config
        self.backend = backend
        self.ccont = CertController(self.config)

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

    def _check_cert2req(self, crt_file, req):
        """
        Check the CSR with the issued certificate.
        This checks the case when the node has regenerated its keys,
        and sends a REGISTER request to master, but the Master already has
        signed certificate with a previous request. Also this could be
        the case of an attacker who tries to send a certificate request
        using the name of a attacked node. We *MUST NOT* return the CRT
        in that case, as this will make the node legally approved!
        """
        crt = None
        if not p.exists(crt_file):
            return False
        try:
            crt = m.X509.load_cert(crt_file)
            if req.verify(crt.get_pubkey()):
                if self.config.security.use_org:
                    return crt.get_subject().OU
                else:
                    return 1
            else:
                return False
        except Exception, ex:
            LOG.exception(ex)
            return False
        finally:
            del crt

    def _build_cert_response(self, node, csr_data, crt_file_name):
        csr = None
        try:
            csr = m.X509.load_request_string(csr_data)
            if not csr:
                return [node, 'INV_CSR']

            cert_id = self._check_cert2req(crt_file_name, csr)
            if cert_id:
                # All is fine, cert is verified to be issued
                # from the sent request and is OK to be send to node
                try:
                    ca_cert = ""
                    if self.config.security.use_org:
                        # Return SubCA+CA
                        subca_cert_file = p.join(p.dirname(p.abspath(
                            self.config.security.ca)),
                            'org', cert_id + '.ca.crt')
                        ca_cert = '%s%s' % (
                            open(subca_cert_file).read(),
                            open(self.config.security.ca).read())
                    else:
                        # Return CA
                        ca_cert = open(self.config.security.ca).read()

                    return [node, 'APPROVED',
                            open(crt_file_name).read() +
                            TOKEN_SEPARATOR +
                            ca_cert +
                            TOKEN_SEPARATOR +
                            open(self.config.security.server_cert).read()]
                except:
                    raise
            else:
                # Issued CRT already exists,
                # and doesn't match current csr
                return [node, 'ERR_CRT_EXISTS']
        except Exception, ex:
            LOG.exception(ex)
            return [node, 'UNKNOWN']
        finally:
            del csr

    def process(self, rq):
        LOG.info("Received admin req: %s %s" % (rq.control, rq.node))

        if rq.control == 'ECHO':
            return [rq.node, rq.data or 'ECHO']

        base_path = p.join(p.dirname(
            p.abspath(self.config.security.ca)))

        try:
            # Check if node is already requested or signed
            csr_file_name = p.join(base_path, 'reqs',
                                   '.'.join([rq.node, 'csr']))
            crt_file_name = p.join(base_path, 'nodes',
                                   '.'.join([rq.node, 'crt']))

            if rq.control == 'IDENT':
                return ['SUB_LOC', 'DEFAULT']

            elif rq.control == 'REGISTER':

                if rq.node in self.ccont.list_approved():
                    # cert already issued
                    return self._build_cert_response(rq.node, rq.data,
                                                     crt_file_name)

                # Saving CSR
                csr = None
                try:
                    csr = m.X509.load_request_string(str(rq.data))
                    CN = csr.get_subject().CN
                    if CN != rq.node:
                        return [rq.node, "ERR_CN_FAIL"]
                    if not is_valid_host(CN):
                        return [rq.node, "ERR_NAME_FORBD"]
                    csr.save(csr_file_name)
                    LOG.info("Saved CSR file: %s" % csr_file_name)
                except Exception, ex:
                    LOG.exception(ex)
                    return [rq.node, 'INV_CSR']
                finally:
                    del csr

                if self.ccont.can_approve(rq.node):
                    sign_res = self.ccont.sign(node=[rq.node])
                    for _, data in sign_res:
                        if data == '%s signed' % rq.node:
                            return self._build_cert_response(rq.node, rq.data,
                                                             crt_file_name)
                    else:
                        return [rq.node, 'APPR_FAIL']
                else:
                    if p.exists(csr_file_name):
                        # Not issued yet
                        return [rq.node, 'PENDING']
                    elif not rq.data:
                        return [rq.node, 'SEND_CSR']
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
