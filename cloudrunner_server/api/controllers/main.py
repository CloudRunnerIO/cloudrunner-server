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
from pecan.secure import secure

from .auth import Auth
# from .batches import Batches
from .clouds import Clouds
from .billing import Billing
from .deployments import Deployments
from .dispatch import Dispatch
from .execute import Execute
from .help import HtmlDocs
from .jobs import Jobs
from .library import Library
from .logs import Logs
from .profile import Profile
from .manage import Manage
from .status import EntityStatus
from .workflows import Workflows

from cloudrunner_server.api import VERSION
from cloudrunner_server.api.util import Wrap
from cloudrunner_server.util.cache import CacheRegistry

LOG = logging.getLogger()


class RestApi(object):

    @classmethod
    def authorize(cls):
        username = (request.headers.get('Cr-User')
                    or request.headers.get('X-Cr-User'))
        token = (request.headers.get('Cr-Token')
                 or request.headers.get('X-Cr-Token'))
        if not username or not token:
            return False

        reg = CacheRegistry()
        with reg.reader('') as cache:
            token = cache.get_user_token(username, token)
            if not token:
                LOG.warn("Missing or expired token for %s" % username)
                return False

            request.user = Wrap(id=token['uid'],
                                username=username,
                                org=token['org'],
                                email=token['email'],
                                email_hash=token['email_hash'],
                                token=token['token'],
                                permissions=token['permissions'],
                                tier=Wrap(**token['tier']))
            return True
        return False

    @classmethod
    def lazy_authorize(cls):
        RestApi.authorize()
        # Always return True
        return True

    @expose('json')
    def version(self):
        return dict(name='CloudRunner.IO REST API', version=VERSION)

    auth = Auth()
    billing = secure(Billing(), 'authorize')
    my = secure(Profile(), 'authorize')
    deployments = secure(Deployments(), 'authorize')
    dispatch = secure(Dispatch(), 'authorize')
    workflows = secure(Workflows(), 'authorize')
    # batches = secure(Batches(), 'authorize')
    library = secure(Library(), 'authorize')
    scheduler = secure(Jobs(), 'authorize')
    logs = secure(Logs(), 'authorize')
    clouds = secure(Clouds(), 'authorize')
    manage = secure(Manage(), 'authorize')

    # Exec
    execute = secure(Execute(), 'lazy_authorize')

    # SSE
    status = EntityStatus()

    # Docs
    html = HtmlDocs()


class Main(object):
    rest = RestApi()
