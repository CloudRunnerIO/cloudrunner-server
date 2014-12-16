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
from cloudrunner_server.api.model.nodes import Node, NodeGroup, Org
from cloudrunner_server.master.functions import CertController

LOG = logging.getLogger()


def _serialize(nodes):
    return [node.name for node in nodes]


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
            groups = NodeGroup.visible(request).all()
            return O._anon(nodes=[n.serialize(
                skip=['id', 'org_id'],
                rel=[('meta', 'meta', json.loads),
                     ('tags', 'tags', lambda lst: [x.value for x in lst])])
                for n in nodes],
                groups=[g.serialize(
                    skip=['id', 'org_id'],
                    rel=[('nodes', 'members', _serialize)]
                ) for g in groups],
                quota=dict(allowed=request.tier.nodes))

    @expose('json', generic=True)
    @check_policy('is_admin')
    @wrap_command(NodeGroup, model_name='Group')
    def nodegroups(self, name=None, **kwargs):
        if name:
            group = NodeGroup.visible(request).filter(
                NodeGroup.name == name).first()
            return O.group(group.serialize(skip=['id', 'org_id']))
        else:
            groups = NodeGroup.visible(request).all()
            return O.groups(_list=[g.serialize(
                skip=['id', 'org_id'],
                rel=[('nodes', 'members', _serialize)]
            ) for g in groups])

    @nodegroups.when(method='POST', template='json')
    @check_policy('is_admin')
    @nodegroups.wrap_modify()
    @wrap_command(NodeGroup, model_name='Group')
    def groups_create(self, name=None, **kwargs):
        if not name:
            return O.error(msg="Name not provided")
        org = request.db.query(Org).filter(
            Org.name == request.user.org).one()
        group = NodeGroup(name=name, org=org)
        request.db.add(group)

    @nodegroups.when(method='PATCH', template='json')
    @check_policy('is_admin')
    @nodegroups.wrap_modify()
    @wrap_command(NodeGroup, model_name='Group')
    def groups_modify(self, name=None, **kwargs):
        group = NodeGroup.visible(request).filter(
            NodeGroup.name == name).first()

        if not group:
            return O.error(msg="Group not found")

        nodes = request.POST.getall('nodes')
        if nodes:
            to_remove = [n for n in group.nodes
                         if n.name not in nodes]
            for n in to_remove:
                group.nodes.remove(n)
            new_nodes = Node.visible(request).filter(
                Node.name.in_(nodes)).all()
            for n in new_nodes:
                group.nodes.append(n)
        else:
            group.nodes[:] = []

        request.db.add(group)

    @nodegroups.when(method='DELETE', template='json')
    @check_policy('is_admin')
    @nodegroups.wrap_delete()
    @wrap_command(NodeGroup, model_name='Group')
    def groups_delete(self, name=None, **kwargs):
        if not name:
            return O.error(msg="Name not provided")

        group = NodeGroup.visible(request).filter(
            NodeGroup.name == name).first()

        if not group:
            return O.error(msg="Group not found")

        request.db.delete(group)

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
        msg, crt_file = cert.sign_node(n.name, ca=request.user.org)
        if not crt_file:
            LOG.error(msg)
            return O.error(msg="Cannot sign node")

    @nodes.when(method='DELETE', template='json')
    @check_policy('is_admin')
    @nodes.wrap_modify()
    def revoke(self, node):
        n = Node.visible(request).filter(Node.name == node).first()
        if not n:
            return O.error(msg="Node not found")
        cert = CertController(conf.cr_config)
        if n.approved:
            msgs = [m[1] for m in cert.revoke(n.name, ca=request.user.org)]
            if ("Certificate for node [%s] revoked" % n.name not in msgs):
                LOG.error(msgs)
                return O.error(msg="Cannot revoke node")
        else:
            msgs = [m[1] for m in cert.clear_req(n.name, ca=request.user.org)]
            if ("Request for node [%s] deleted" % n.name not in msgs):
                LOG.error(msgs)
                return O.error(msg="Cannot delete node request")
