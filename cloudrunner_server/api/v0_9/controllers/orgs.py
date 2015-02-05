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

from cloudrunner_server.api.decorators import wrap_command
from cloudrunner_server.api.model import Org
from cloudrunner_server.api.util import JsonOutput as O
from cloudrunner_server.api.policy.decorators import check_policy

LOG = logging.getLogger()


class Orgs(object):

    # ORGS ###########
    #

    @expose('json', generic=True)
    @check_policy('is_super_admin')
    @wrap_command(Org, model_name='Organization')
    def orgs(self, *args, **kwargs):
        orgs = [o.serialize(skip=['id', 'cert_ca', 'cert_key'])
                for o in request.db.query(Org).all()]
        return O.orgs(_list=orgs)

    @check_policy('is_super_admin')
    @orgs.when(method='POST', template='json')
    @orgs.wrap_create()
    def create_org(self, *args, **kwargs):
        name = kwargs['org']
        org = Org(name=name, enabled=True)
        request.db.add(org)

    @orgs.when(method='PATCH', template='json')
    @check_policy('is_super_admin')
    @orgs.wrap_modify()
    def toggle(self, name=None, status=None, *args, **kwargs):
        name = name or kwargs['name']
        status = status or kwargs['status']
        status = bool(status in ['1', 'True', 'true'])
        org = request.db.query(Org).filter(
            Org.name == name, Org.enabled != status).first()

        if org:
            org.enabled = status
            request.db.add(org)

    @orgs.when(method='DELETE', template='json')
    @check_policy('is_super_admin')
    @orgs.wrap_delete()
    def remove(self, name=None, **kwargs):
        name = name or kwargs['name']
        org = request.db.query(Org).filter(
            Org.name == name, Org.enabled != True).first()  # noqa

        if not org:
            return O.error(msg="Organization not found or is enabled")

        if org:
            request.db.delete(org)
