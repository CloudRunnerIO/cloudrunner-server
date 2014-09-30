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

import json
import logging
from pecan import expose, request, conf

from cloudrunner_server.api.decorators import wrap_command
from cloudrunner_server.api.util import JsonOutput as O
from cloudrunner_server.api.policy.decorators import check_policy
from cloudrunner_server.api.model.nodes import Node
from cloudrunner_server.master.functions import CertController

LOG = logging.getLogger()


class Nodes(object):

    @expose('json', generic=True)
    @check_policy('is_admin')
    @wrap_command(Node, model_name='Node')
    def nodes(self, name=None, **kwargs):
        if name:
            node = Node.visible(request).filter(Node.name == name).first()
            return O.node(node.serialize(skip=['id', 'org_id']))
        else:
            nodes = Node.visible(request).all()
            return O.nodes(_list=[n.serialize(
                skip=['id', 'org_id'],
                rel=[('meta', 'meta', json.loads)])
                for n in nodes])

    @nodes.when(method='PUT', template='json')
    @check_policy('is_admin')
    @nodes.wrap_modify()
    def approve(self, node=None, **kwargs):
        node = node or kwargs['node']
        n = Node.visible(request).filter(Node.name == node,
                                         Node.approved == False).first()  # noqa
        if not n:
            return O.error(msg="Node not found")
        cert = CertController(conf.cr_config)
        msg, crt_file = cert.sign_node(n.name)
        if not crt_file:
            LOG.error(msg)
            return O.error(msg="Cannot sign node")

    @nodes.when(method='DELETE', template='json')
    @check_policy('is_admin')
    @nodes.wrap_modify()
    def revoke(self, node):
        n = Node.visible(request).filter(Node.name == node,
                                         Node.approved == True).first()  # noqa
        if not n:
            return O.error(msg="Node not found")
        cert = CertController(conf.cr_config)
        msgs = [m for m in cert.revoke(n.name)]
        if ("Certificate for node [%s] revoked" % n.name not in msgs):
            LOG.error(msgs)
            return O.error(msg="Cannot revoke node")
