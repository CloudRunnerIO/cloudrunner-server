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
from pecan.hooks import HookController

from cloudrunner.core import parser
from cloudrunner_server.api.hooks.error_hook import ErrorHook
from cloudrunner_server.api.hooks.db_hook import DbHook
from cloudrunner_server.api.hooks.perm_hook import PermHook
from cloudrunner_server.api.decorators import wrap_command
from cloudrunner_server.api.model import Script
from cloudrunner_server.api.util import JsonOutput as O

LOG = logging.getLogger()
WHERE = {
    'include': 'before',
    'include-before': 'before',
    'include-after': 'after',
}


class Workflows(HookController):

    __hooks__ = [ErrorHook(), DbHook(),
                 PermHook(dont_have=set(['is_super_admin']))]

    @expose('json', generic=True)
    @wrap_command(Script, model_name='Workflow')
    def workflow(self, *args, **kwargs):
        if not args:
            return O.error(msg="Path not provided")
        path = '/'.join(args)
        rev = kwargs.get("rev")
        script = Script.find(request, path).one()

        revision = script.contents(request, rev=rev)
        sections = parser.parse_sections(revision.content)
        data = []

        for s in sections:
            includes = []
            atts = []
            options = {}
            if s.args:
                for arg, vals in s.args.items():
                    if arg in ('include-before', 'include-after'):
                        includes.extend([dict(path=scr_name, where=WHERE[arg])
                                         for scr_name in vals])
                    elif arg == 'attach':
                        atts.extend([dict(path=scr_name) for scr_name in vals])
                    else:
                        options[arg] = vals

            section = dict(content=s.body,
                           targets=[t.strip() for t in s.target.split(' ')
                                    if t.strip()],
                           lang=s.lang,
                           includes=includes,
                           attachments=atts,
                           timeout=s.timeout)
            data.append(section)

        return O.workflow(rev=revision.version, sections=data)

    @workflow.when(method='POST', template='json')
    @wrap_command(Script, model_name='Workflow')
    def preview(self, *args, **kwargs):
        if not args:
            return O.error(msg="Path not provided")
        path = '/'.join(args)
        script = Script.find(request, path).one()
        print script
        # request.db.add(group)

    @workflow.when(method='PUT', template='json')
    @wrap_command(Script, model_name='Workflow')
    def save(self, *args, **kwargs):
        if not args:
            return O.error(msg="Path not provided")
        if not request.json:
            return O.error(msg="Data not provided")

        workflow = request.json['workflow']
        path = '/'.join(args)
        script = Script.find(request, path).one()
        print script, workflow
