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
from pecan import expose, request

from cloudrunner_server.api.model import Group, Org, User, ApiKey, joinedload
from cloudrunner_server.api.util import JsonOutput as O
from cloudrunner_server.api.policy.decorators import check_policy
from cloudrunner_server.api.decorators import wrap_command

LOG = logging.getLogger()


class Users(object):

    @expose('json', generic=True)
    @check_policy('is_admin')
    @wrap_command(User)
    def users(self, name=None, *args, **kwargs):
        def modifier(roles):
            return [dict(as_user=role.as_user, servers=role.servers)
                    for role in roles]
        if name:
            user = User.visible(request).filter(User.username == name).first()
            return O.user(user.serialize(
                skip=['id', 'org_id', 'password'],
                rel=[('groups.name', 'groups')]))
        else:
            users = [u.serialize(
                skip=['id', 'org_id', 'password'],
                rel=[('groups.name', 'groups')])
                for u in User.visible(request).options(
                    joinedload(User.groups)).all()]
            groups = [u.serialize(
                skip=['id', 'org_id'],
                rel=[('roles', 'roles', modifier),
                     ('users', 'users', lambda us: [u.username for u in us]),
                     ])
                for u in Group.visible(request).options(
                    joinedload(Group.users)).options(
                        joinedload(Group.roles)).all()]
            return O._anon(users=users,
                           groups=groups,
                           quota=dict(users=request.user.tier.users,
                                      groups=request.user.tier.groups))

    @users.when(method='POST', template='json')
    @check_policy('is_admin')
    @users.wrap_create()
    def create(self, username=None, *args, **kwargs):
        username = username or kwargs['username']
        email = kwargs['email']
        password = kwargs['password']
        first_name = kwargs['first_name']
        last_name = kwargs['last_name']
        department = kwargs['department']
        position = kwargs['position']

        org = request.db.query(Org).filter(
            Org.name == request.user.org).one()
        new_user = User(username=username, email=email,
                        first_name=first_name, last_name=last_name,
                        department=department, position=position, org=org)
        new_user.set_password(password)
        request.db.add(new_user)

    @users.when(method='PATCH', template='json')
    @check_policy('is_admin')
    @users.wrap_modify()
    def patch(self, username=None, *args, **kwargs):
        name = username
        user = User.visible(request).filter(User.username == name).first()
        if not user:
            return O.error(msg="User not found")

        if not user.enabled:
            # Allow only enabling
            enable = kwargs.get("enable")
            if not enable or enable not in ["1", "true", "True"]:
                return O.error(msg="Cannot modify inactive user")
            user.enabled = True

        for k in set(kwargs.keys()).intersection(User.attrs):
            setattr(user, k, kwargs[k])

        groups = request.POST.getall('groups')
        if groups:
            to_remove = [g for g in user.groups
                         if g.name not in groups]
            for g in to_remove:
                user.groups.remove(g)
            grps = Group.visible(request).filter(
                Group.name.in_(groups)).all()
            for g in grps:
                user.groups.append(g)
        else:
            user.groups[:] = []
        password = kwargs.get('password')
        if password:
            user.set_password(password)
        phone = kwargs.get('phone')
        if phone:
            user.phone = phone
        request.db.add(user)

    @users.when(method='PUT', template='json')
    @users.wrap_modify()
    def update(self, *args, **kwargs):
        # assert all values
        (kwargs['username'], kwargs['first_name'], kwargs['phone'],
         kwargs['last_name'], kwargs['department'], kwargs['position'])
        return self.patch(**kwargs)

    @users.when(method='DELETE', template='json')
    @check_policy('is_admin')
    @users.wrap_delete()
    def delete(self, username, *args):
        name = username
        user = User.visible(request).filter(User.username == name).first()
        if not user:
            return O.error(msg="User not found")

        request.db.delete(user)

    @expose('json', generic=True)
    @wrap_command(ApiKey)
    def apikeys(self, *args):
        keys = request.db.query(ApiKey).join(User).filter(
            User.id == request.user.id).all()
        return O._anon(keys=[k.serialize(skip=['id', 'user_id'])
                             for k in keys],
                       quota=dict(allowed=request.user.tier.api_keys))

    @apikeys.when(method='POST', template='json')
    @apikeys.wrap_create()
    def apikeys_create(self, *args, **kwargs):
        description = kwargs.get('description', "")
        user = request.db.query(User).filter(User.id == request.user.id).one()
        key = ApiKey(user=user, description=description,
                     enabled=True)
        request.db.add(key)
        request.db.commit()
        return O.key(**key.serialize(skip=['id', 'user_id']))

    @apikeys.when(method='PATCH', template='json')
    @apikeys.wrap_modify()
    def apikeys_modify(self, value, *args, **kwargs):
        key = request.db.query(ApiKey).join(User).filter(
            User.id == request.user.id, ApiKey.value == value).one()
        if not key:
            return O.error(msg="Api Key not found")

        if 'description' in kwargs:
            description = kwargs['description']
            key.description = description
        if 'enabled' in kwargs:
            enabled = kwargs.get('enabled') not in ['0', 'false', 'False']
            key.enabled = enabled
        request.db.add(key)

    @apikeys.when(method='PUT', template='json')
    @apikeys.wrap_modify()
    def apikeys_replace(self, value, *args, **kwargs):
        description = kwargs['description']
        enabled = kwargs['enabled']
        description = kwargs.get('description', "")
        self.apikeys_modify(value, description=description, enabled=enabled)

    @apikeys.when(method='DELETE', template='json')
    @apikeys.wrap_delete()
    def apikeys_delete(self, apikey, *args):
        key = request.db.query(ApiKey).join(User).filter(
            User.id == request.user.id, ApiKey.value == apikey).one()
        request.db.delete(key)
