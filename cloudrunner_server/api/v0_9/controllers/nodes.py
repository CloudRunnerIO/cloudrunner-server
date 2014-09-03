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
from pecan import expose, request  # noqa
from sqlalchemy.exc import IntegrityError

from cloudrunner_server.api.util import JsonOutput as O
from cloudrunner_server.api.policy.decorators import check_policy
from cloudrunner_server.api.model.nodes import Node

LOG = logging.getLogger()


class Nodes(object):

    @expose('json', generic=True)
    @check_policy('is_admin')
    def nodes(self, name=None, **kwargs):
        if name:
            node = Node.visible(request).filter(Node.name == name).first()
            return O.node(node.serialize(skip=['id', 'org_id']))
        else:
            nodes = Node.visible(request).all()
            return O.nodes(_list=[n.serialize(skip=['id', 'org_id'])
                                  for n in nodes])

    @nodes.when(method='PUT', template='json')
    @check_policy('is_admin')
    def modify(self, node=None, **kwargs):
        try:
            node = node or kwargs['node']
            return O.success(status="ok")
        except KeyError, kerr:
            return O.error(msg="Field not present: '%s'" % kerr,
                           field=str(kerr))
        except IntegrityError:
            request.db.rollback()
            return O.error(msg="Username is already taken by another user",
                           field="username")
        except Exception, ex:
            LOG.exception(ex)
            request.db.rollback()
            return O.error(msg="Cannot create user")
