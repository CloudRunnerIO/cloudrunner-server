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

from cloudrunner_server.api.decorators import wrap_command
from cloudrunner_server.api.model import Group, Org, Role
from cloudrunner_server.api.policy.decorators import check_policy
from cloudrunner_server.api.util import JsonOutput as O

LOG = logging.getLogger()


class Groups(object):

    @expose('json', generic=True)
    @check_policy('is_admin')
    @wrap_command(Group)
    def groups(self, name=None, *args):
        def modifier(roles):
            return [dict(as_user=role.as_user, servers=role.servers)
                    for role in roles]
        if name:
            group = Group.visible(request).filter(Group.name == name).first()
            return O.group(group.serialize(
                skip=['id', 'org_id'],
                rel=[('roles', 'roles', modifier)]))
        else:
            groups = [u.serialize(
                skip=['id', 'org_id'],
                rel=[('roles', 'roles', modifier)])
                for u in Group.visible(request).all()]
            return O._anon(groups=groups,
                           quota=dict(allowed=request.user.tier.groups))

    @groups.when(method='POST', template='json')
    @check_policy('is_admin')
    @groups.wrap_create()
    def add_group(self, name, *args, **kwargs):
        name = name or kwargs['name']
        org = request.db.query(Org).filter(
            Org.name == request.user.org).one()
        group = Group(name=name, org=org)
        request.db.add(group)
        request.db.commit()

    @groups.when(method='PUT', template='json')
    @check_policy('is_admin')
    @groups.wrap_modify()
    def modify_group_roles(self, name, *args, **kwargs):
        name = name or kwargs['name']
        add_roles = request.POST.getall('add')
        rm_roles = request.POST.getall('remove')
        group = Group.visible(request).filter(Group.name == name).first()
        if not group:
            return O.error(msg="Group is not available")

        for role in rm_roles:
            as_user, _, servers = role.rpartition("@")
            if not as_user or not servers:
                continue
            if as_user == "*":
                as_user = "@"
            roles = [r for r in group.roles if r.as_user == as_user and
                     r.servers == servers]
            for r in roles:
                request.db.delete(r)
        request.db.commit()

        errs = []
        for role in add_roles:
            as_user, _, servers = role.rpartition("@")
            if not Role.is_valid(as_user):
                errs.append(as_user)
        if errs:
            if len(errs) == 1:
                return O.error(msg="The role '%s' is not valid" % errs[0])
            else:
                return O.error(msg="The following roles are not valid: %s" %
                               ", ".join(errs))

        for role in add_roles:
            as_user, _, servers = role.rpartition("@")
            if not as_user or not servers:
                continue
            if as_user == "*":
                as_user = "@"
            r = Role(as_user=as_user, servers=servers, group=group)
            try:
                request.db.add(r)
                request.db.commit()
            except IntegrityError:
                request.db.rollback()

    @groups.when(method='DELETE', template='json')
    @check_policy('is_admin')
    @groups.wrap_delete()
    def rm_group(self, name, *args):
        group = Group.visible(request).filter(Group.name == name).first()
        if not group:
            return O.error(msg="Group not found")

        request.db.delete(group)
        request.db.commit()
