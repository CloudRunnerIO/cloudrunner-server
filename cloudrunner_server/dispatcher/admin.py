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

from datetime import datetime
import json
import logging
from threading import Thread
from sqlalchemy import create_engine, event
from sqlalchemy.orm import scoped_session, sessionmaker

from cloudrunner.core.exceptions import ConnectionError
from cloudrunner.core.message import (ADMIN_TOWER, M, Control)
from cloudrunner_server.util.db import checkout_listener
from cloudrunner_server.api.model import metadata, Node, NodeTag, Org
from cloudrunner_server.master.functions import (CertController,
                                                 CertificateExists)
from cloudrunner_server.plugins.auth.base import NodeVerifier

LOG = logging.getLogger('Control Tower')


class OrgVerifier(NodeVerifier):

    def __init__(self, config):
        pass

    def verify(self, node, subject, **kwargs):
        org = self.db.query(Org).filter(Org.uid == subject.OU).first()
        if org:
            return org.name


class Admin(Thread):

    """
    Admin class to process control requests like Register, etc.
    """

    def __init__(self, config, backend):
        super(Admin, self).__init__()
        self.config = config
        self.backend = backend
        self.db_path = config.db
        self.ccont = CertController(config)

    def set_context_from_config(self, recreate=None, **configuration):
        session = scoped_session(sessionmaker())
        engine = create_engine(self.db_path, **configuration)
        if 'mysql+pymysql://' in self.db_path:
            event.listen(engine, 'checkout', checkout_listener)
        session.bind = engine
        metadata.bind = session.bind
        if recreate:
            # For tests: re-create tables
            metadata.create_all(engine)
        self.db = session
        OrgVerifier.db = session

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
                    req = M.build(packed[0])
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

        if req.control == 'ECHO':
            return [req.node, req.data or 'ECHO']
        if req.control == 'REGISTER':
            try:
                tags = []
                node = Node(name=req.node, meta=json.dumps(req.meta))
                try:
                    valid, msg, org, tags = self.ccont.validate_request(
                        req.node, req.data)
                    if not valid:
                        LOG.info("Request validation result: %s" % msg)
                except CertificateExists, cex:
                    LOG.error("Certificate exists for node %s[%s]" % (
                        req.node, cex.org))
                    valid, cert_or_msg = self.ccont.build_cert_chain(
                        req.node, cex.org, req.data)
                    if valid:
                        node = self.db.query(Node).join(Org).filter(
                            Node.name == req.node, Org.name == cex.org).one()
                        if node.approved:
                            return Control(req.node, 'APPROVED', cert_or_msg)
                        node.approved = True
                        node.approved_at = datetime.now()
                        self.db.commit()
                        return Control(req.node, 'APPROVED', cert_or_msg)
                    else:
                        return Control(req.node, 'REJECTED', cert_or_msg)

                if not valid:
                    return Control(req.node, 'REJECTED', "INV_CSR")
                if org:
                    org_ = self.db.query(Org).filter(Org.name == org).one()
                    node.org = org_

                for tag in tags:
                    t = NodeTag(value=tag)
                    self.db.add(t)
                    node.tags.append(t)

                if not self.ccont.can_approve(req.node):
                    node.approved = False
                    self.db.add(node)
                    self.db.commit()
                    return Control(req.node, 'REJECTED', 'PENDING')

                msgs, cert_file = self.ccont.sign_node(req.node, ca=org)
                approved = bool(cert_file)
                if not approved:
                    LOG.warn(msgs)
                else:
                    LOG.info("Request approved")

                node.approved = approved
                if approved:
                    node.approved_at = datetime.now()
                self.db.add(node)
                self.db.commit()
                if approved:
                    success, cert_or_msg = self.ccont.build_cert_chain(
                        req.node, org, req.data)
                    if success:
                        return Control(req.node, 'APPROVED', cert_or_msg)
                    else:
                        return Control(req.node, 'REJECTED', cert_or_msg)
                else:
                    return Control(req.node, 'REJECTED', "APPR_FAIL")
            except Exception, ex:
                self.db.rollback()
                LOG.error(ex)
                return Control(req.node, 'REJECTED', 'APPR_FAIL')

        return None

    def close(self, *args):
        LOG.info("Stopping Admin Process")
        self.admin_endp.close()
        self.node_reply_queue.close()
        LOG.info("Stopped admin Process")
