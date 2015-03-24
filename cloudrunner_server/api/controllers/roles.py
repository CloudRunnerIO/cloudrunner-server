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
from cloudrunner_server.api.model import Role, User
from cloudrunner_server.api.util import JsonOutput as O
from cloudrunner_server.api.policy.decorators import check_policy

LOG = logging.getLogger()
#
# ROLES ##########
#


class Roles(object):

    @expose('json', generic=True)
    @check_policy('is_admin')
    @wrap_command(Role)
    def roles(self, username=None, *args):
        user = User.visible(request).filter(User.username == username).one()
        roles = []

        def append_roles(r):
            return roles.extend(r)

        map(append_roles, [group.roles for group in user.groups])
        roles.extend(user.roles)
        return O.roles(roles=[r.serialize(
            skip=['id', 'group_id', 'user_id'],
            rel=([('group.name', 'group')])) for r in roles],
            quota=dict(allowed=request.user.tier.roles))

    @roles.when(method='POST', template='json')
    @check_policy('is_admin')
    @roles.wrap_create()
    def add_role(self, username=None, **kwargs):
        user = User.visible(request).filter(User.username == username).one()
        as_user = str(kwargs['as_user'])
        servers = kwargs['servers']
        if as_user == '*':
            as_user = "@"
        elif not Role.is_valid(as_user):
            return O.error(msg="Invalid user name: %s" % as_user)
        role = Role(as_user=as_user, servers=servers)
        user.roles.append(role)
        request.db.commit()

    @roles.when(method='DELETE', template='json')
    @check_policy('is_admin')
    @roles.wrap_modify()
    def rm_role(self, username=None, as_user=None, servers=None):
        user = User.visible(request).filter(User.username == username).one()
        role = [r for r in user.roles
                if r.as_user == as_user and r.servers == servers]

        if role:
            map(request.db.delete, role)
        request.db.commit()
