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
from cloudrunner_server.api.model import Script, Revision
from cloudrunner_server.api.util import JsonOutput as O
from cloudrunner_server.triggers.manager import _parse_script_name

LOG = logging.getLogger()


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
            atts = []
            include_before = []
            include_after = []
            options = {}
            if s.args:
                for arg, vals in s.args.items():
                    if arg == 'include-before':
                        include_before.extend([dict(path=scr_name)
                                               for scr_name in vals])
                    elif arg == 'include-after':
                        include_after.extend([dict(path=scr_name)
                                              for scr_name in vals])
                    elif arg == 'attach':
                        atts.extend([dict(path=scr_name) for scr_name in vals])
                    else:
                        options[arg] = vals

            section = dict(content=s.body,
                           targets=[t.strip() for t in s.target.split(' ')
                                    if t.strip()],
                           lang=s.lang,
                           include_before=include_before,
                           include_after=include_after,
                           attachments=atts,
                           timeout=s.timeout)
            data.append(section)

        return O.workflow(rev=revision.version, sections=data)

    @workflow.when(method='POST', template='json')
    @wrap_command(Script, model_name='Workflow')
    def preview(self, *args, **kwargs):
        if not args:
            return O.error(msg="Path not provided")
        expand = kwargs.get('expand') in ['1', 'true', 'True', 'on']
        workflow = request.json['workflow']

        new_content = flatten_workflow(workflow, expand=expand)
        path = '/'.join(args)

        return O.script(path=path, content="\n".join(new_content))

    @workflow.when(method='PUT', template='json')
    @wrap_command(Script, model_name='Workflow')
    def save(self, *args, **kwargs):
        if not args:
            return O.error(msg="Path not provided")
        if not request.json:
            return O.error(msg="Data not provided")

        workflow = request.json['workflow']

        new_content = flatten_workflow(workflow)
        path = '/'.join(args)
        script = Script.find(request, path).one()
        rev = Revision(content='\n'.join(new_content), script_id=script.id)
        request.db.add(rev)


def flatten_workflow(workflow, expand=False):
    new_content = []
    header = ("#! switch [%(targets)s] %(include_before)s %(include_after)s "
              "%(attachments)s %(timeout)s")
    for section in workflow['sections']:
        targets = " ".join(section['targets'])
        timeout = section['timeout'] or ''
        lang = section.get('lang')
        shebang_lang = ""
        if lang and lang != 'bash':
            shebang_lang = "#! /usr/bin/%s" % lang
        if timeout:
            timeout = '--timeout=%s' % timeout
        include_before = ['--include-before=%s' % i['path']
                          for i in section.get('include_before', [])]
        include_after = ['--include-after=%s' % i['path']
                         for i in section.get('include_after', [])]
        attachments = ['--attach=%s' % i['path']
                       for i in section['attachments']]

        if expand:
            parts = []
            for ins, scr in enumerate(section.get('include_before', [])):
                try:
                    s = _parse_script_name(request, scr['path']).content
                except:
                    s = '# Script %s cannot be loaded' % scr['path']
                parts.insert(ins, s)

            for scr in section.get('include_after', []):
                try:
                    s = _parse_script_name(request, scr['path']).content
                except:
                    s = '# Script %s cannot be loaded' % scr['path']
                parts.append(s)

            include_before = []
            include_after = []
        else:
            parts = [section['content']]
        _header = header % dict(targets=targets,
                                include_before=" ".join(include_before),
                                include_after=" ".join(include_after),
                                attachments=" ".join(attachments),
                                timeout=timeout)

        new_content.append(_header)
        if shebang_lang:
            new_content.append(shebang_lang)
        new_content.extend(parts)
    return new_content
