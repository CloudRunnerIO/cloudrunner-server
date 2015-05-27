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
from pecan.hooks import HookController

from cloudrunner_server.api.decorators import wrap_command
from cloudrunner_server.api.hooks.error_hook import ErrorHook
from cloudrunner_server.api.hooks.db_hook import DbHook
from cloudrunner_server.api.hooks.perm_hook import PermHook
from cloudrunner_server.api.model import (CloudProfile, CloudShare, User)
from cloudrunner_server.api.policy.decorators import check_policy
from cloudrunner_server.api.util import JsonOutput as O, random_token

LOG = logging.getLogger()


class Clouds(HookController):
    __hooks__ = [ErrorHook(), DbHook(),
                 PermHook(dont_have=set(['is_super_admin']))]

    @expose('json', generic=True)
    @wrap_command(CloudProfile, model_name='Cloud Profile')
    def profiles(self, name=None, *args):
        def shares(p):
            return [sh.serialize(
                skip=['id', 'profile_id', 'password']) for sh in p]

        def nodes(ns):
            return [n.name for n in ns]

        def shares_details(p):
            return [sh.serialize(
                skip=['id', 'profile_id', 'password'],
                rel=[('shared_nodes', 'nodes', nodes)]
            ) for sh in p]
        if name:
            prof = CloudProfile.my(request).filter(
                CloudProfile.name == name).first()

            return O.profile(prof.serialize(
                skip=['id', 'owner_id', 'share_id', 'password', 'arguments'],
                rel=[('shares', 'shares', shares_details)]))
        else:
            profs = [p.serialize(
                skip=['id', 'owner_id', 'share_id', 'password', 'arguments'],
                rel=[('shares', 'shares', shares)])
                for p in CloudProfile.my(request).all()]
            return O._anon(profiles=profs)

    @profiles.when(method='POST', template='json')
    @check_policy('is_admin')
    @profiles.wrap_create()
    def add_profile(self, name, *args, **kwargs):
        p_type = kwargs['type']
        user = User.visible(request).filter(
            User.id == request.user.id).first()
        name = name or kwargs['name']

        if p_type == "shared":
            username = kwargs.pop('username')
            password = kwargs.pop('password')
            share = request.db.query(CloudShare).filter(
                CloudShare.name == username,
                CloudShare.password == password).first()
            if not share:
                return O.error(msg="The specified shared profile is not found")
            prof = CloudProfile(name=name, username=username,
                                password=password,
                                owner=user,
                                type=share.profile.type,
                                shared=share.profile)
            request.db.add(prof)
        else:
            username = kwargs.pop('username')
            password = kwargs.pop('password')
            arguments = kwargs.pop('arguments')
            clear_nodes = (bool(kwargs.get('clear_nodes'))
                           and not kwargs.get('clear_nodes')
                           in ['0', 'false', 'False'])

            prof = CloudProfile(name=name, username=username,
                                password=password, arguments=arguments,
                                owner=user,
                                clear_nodes=clear_nodes,
                                type=p_type)
            request.db.add(prof)

    @profiles.when(method='PUT', template='json')
    @check_policy('is_admin')
    @profiles.wrap_modify()
    def modify_profile(self, name, *args, **kwargs):
        username = kwargs.pop('username')
        password = kwargs.pop('password')
        arguments = kwargs.pop('arguments')
        name = name or kwargs['name']
        prof = CloudProfile.my(request).filter(
            CloudProfile.name == name).first()
        if prof:
            prof.username = username
            prof.password = password
            prof.arguments = arguments
            request.db.add(prof)
        else:
            return O.error(msg="Cannot find profile %s" % name)

    @profiles.when(method='DELETE', template='json')
    @check_policy('is_admin')
    @profiles.wrap_delete()
    def rm_profile(self, name, *args):
        prof = CloudProfile.my(request).filter(
            CloudProfile.name == name).first()
        if not prof:
            return O.error(msg="Cannot find profile %s" % name)
        request.db.delete(prof)

    @expose('json', generic=True)
    @wrap_command(CloudShare, model_name='Cloud Share')
    def shares(self, profile, *args, **kwargs):

        def nodes(p):
            return []

        if args:
            sh = CloudShare.my(request, profile).filter(
                CloudShare.name == args[0]).first()
            return O.share(sh.serialize(
                skip=['id', 'profile_id'],
                rel=[('shared_nodes', 'nodes', nodes)]))
        else:
            profs = [p.serialize(
                skip=['id', 'profile_id', 'password'],
                rel=[('shared_nodes', 'nodes', nodes)])
                for p in CloudShare.my(request, profile).all()]
            return O._anon(shares=profs)

    @shares.when(method='POST', template='json')
    @check_policy('is_admin')
    @shares.wrap_modify(integrity_error=lambda er:
                        "Duplicate share name for the same profile")
    def add_share(self, profile, *args, **kwargs):
        name = kwargs.get('name')
        node_quota = int(kwargs.get('node_quota', 0))
        if not name:
            return O.error(msg="Name if required")

        prof = CloudProfile.my(request).filter(
            CloudProfile.name == profile).first()
        if not prof:
            return O.error(msg="Cloud Profile '%s' not found" % profile)

        share = CloudShare(name=name, password=random_token(length=64),
                           node_quota=node_quota, profile=prof)
        request.db.add(share)

    @shares.when(method='DELETE', template='json')
    @check_policy('is_admin')
    @shares.wrap_delete()
    def rm_share(self, profile, name, *args):
        share = CloudShare.my(request, profile).filter(
            CloudShare.name == name).first()
        request.db.delete(share)
