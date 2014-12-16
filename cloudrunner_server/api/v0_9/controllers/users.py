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

from cloudrunner_server.api.model import Group, Org, User, ApiKey
from cloudrunner_server.api.util import JsonOutput as O
from cloudrunner_server.api.policy.decorators import check_policy
from cloudrunner_server.api.decorators import wrap_command

LOG = logging.getLogger()

USER_ATTR = set(['username', 'email', 'first_name',
                 'last_name', 'department', 'position'])


class Users(object):

    @check_policy('is_admin')
    @expose('json', generic=True)
    @wrap_command(User)
    def users(self, name=None, *args, **kwargs):
        if name:
            user = User.visible(request).filter(User.username == name).first()
            return O.user(user.serialize(
                skip=['id', 'org_id', 'password'],
                rel=[('groups.name', 'groups')]))
        else:
            users = [u.serialize(
                skip=['id', 'org_id', 'password'],
                rel=[('groups.name', 'groups')])
                for u in User.visible(request).all()]
            return O._anon(users=users, quota=dict(allowed=request.tier.users))

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

        for k in set(kwargs.keys()).intersection(USER_ATTR):
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
        request.db.add(user)

    @users.when(method='PUT', template='json')
    @users.wrap_modify()
    def update(self, *args, **kwargs):
        # assert all values
        (kwargs['username'], kwargs['email'], kwargs['first_name'],
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
        return O.keys([k.serialize(skip=['id', 'user_id']) for k in keys])

    @apikeys.when(method='POST', template='json')
    @apikeys.wrap_create()
    def apikeys_create(self, *args):
        key = ApiKey(user_id=request.user.id)
        request.db.add(key)
        request.db.commit()
        return O.key(**key.serialize(skip=['id', 'user_id']))

    @apikeys.when(method='DELETE', template='json')
    @apikeys.wrap_delete()
    def apikeys_delete(self, apikey, *args):
        key = request.db.query(ApiKey).join(User).filter(
            User.id == request.user.id, ApiKey.value == apikey).one()
        request.db.delete(key)
