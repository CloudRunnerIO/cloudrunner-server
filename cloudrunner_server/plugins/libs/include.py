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
import re
from sqlalchemy import or_
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

from cloudrunner_server.plugins.args_provider import ArgsProvider
from cloudrunner_server.plugins.libs.base import IncludeLibPluginBase
from cloudrunner_server.plugins.args_provider import ManagedPlugin
from cloudrunner.util.http import parse_url, load_from_link
from cloudrunner_server.api.model import *  # noqa

LOG = logging.getLogger(__name__)
PROTO_RE = re.compile(r'^(ht|f|sf)+tp[s]*://([^/]+/){1}')


def sanitize(lib):
    return PROTO_RE.sub('', lib)


class LibIncludePlugin(IncludeLibPluginBase, ArgsProvider, ManagedPlugin):

    def __init__(self):
        pass

    @classmethod
    def start(cls, config):
        LOG.info("Starting Library Plugin")
        engine = create_engine(config.users.db)
        session = scoped_session(sessionmaker(bind=engine,
                                              autocommit=True))
        metadata.bind = session.bind
        cls.session = session

    @classmethod
    def stop(cls):
        LOG.info("Stopping Library Plugin")

    def append_args(self):
        return [dict(arg='--attach-lib', dest='attachlib', action='append'),
                dict(arg='--include-lib', dest='includelib', action='append')]

    def show(self, user_org, name, **kwargs):
        proto_host = parse_url(name)
        if proto_host:
            return self._load_url(proto_host[0], proto_host[1], **kwargs)
        else:
            return self._load_local(user_org, name, **kwargs)

    def _load_url(self, proto_host, name, **kwargs):
        reply, data = load_from_link(proto_host, name)
        return reply == 0, ['N/A', data]

    def _load_local(self, user_org, name, **kwargs):
        inl = self.session.query(Inline).join(User, Org).filter(
            Inline.name == name, Org.name == user_org[1],
                or_(Inline.private == None,  # noqa
                    Inline.private == False,  # noqa
                    User.username == user_org[0])).first()

        if inl:
            return True, inl.content

        return (False, None)

    def process(self, user_org, section, env, args):
        """
        --include-lib supports multiple options
            or single option with multiple values,
            separated by semi-colon(:)
        """
        if args.includelib or args.attachlib:
            arr = []

            if args.includelib:
                args.includelib = [a.strip("\"'") for a in args.includelib]
            if args.attachlib:
                args.attachlib = [a.strip("\"'") for a in args.attachlib]

            def _append(_list, elem):
                _list.extend(elem.split(';'))
                return _list

            reduce(_append, args.includelib or args.attachlib, arr)
            for lib in arr:
                exists, source = self.show(user_org, lib)
                lib = sanitize(lib)
                if exists:
                    yield dict(name=lib,
                               inline=bool(args.includelib),
                               source=source)
