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

from functools import partial
import logging
from pecan import expose, request, redirect, response
from pecan.hooks import HookController
import pytz

from cloudrunner.core import parser
from cloudrunner_server.api.hooks.error_hook import ErrorHook
from cloudrunner_server.api.hooks.db_hook import DbHook
from cloudrunner_server.api.hooks.perm_hook import PermHook
from cloudrunner_server.api.decorators import wrap_command
from cloudrunner_server.api.model import Script, Revision, Folder
from cloudrunner_server.api.util import JsonOutput as O
from cloudrunner_server.triggers.manager import include_substitute
from cloudrunner_server.plugins.repository.base import (PluginRepoBase,
                                                        NotModified,
                                                        NotAccessible)

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
        repo_path, lib_path, scr_path, _ = Script.parse(path)
        repo = script.folder.repository

        data = []

        editable = repo.editable(request)
        if repo.type == "cloudrunner":
            revision = script.contents(request, rev=rev)
        else:
            plugin = PluginRepoBase.find(repo.type)
            parent_repo = [r for r in repo.parents
                           if r.org.name == request.user.org][0]
            if not plugin:
                return O.error(msg="Plugin for repo type %s not found!" %
                               repo.type)
            plugin = plugin(parent_repo.credentials.auth_user,
                            parent_repo.credentials.auth_pass,
                            parent_repo.credentials.auth_args)

            try:
                contents, last_modified, version, etag = plugin.contents(
                    repo.name, "".join([lib_path, scr_path]),
                    last_modified=script.etag, rev=rev)
                script.created_at = last_modified
                script.etag = etag
                exists = script.contents(request, rev=rev)
                if not exists:
                    exists = Revision(created_at=last_modified,
                                      version=version, script=script,
                                      content=contents)
                else:
                    exists.content = contents
                    exists.created_at = last_modified
                request.db.add(script)
                revision = exists
                request.db.add(revision)
            except NotModified:
                revision = script.contents(request, rev=rev)
            except NotAccessible:
                return O.error(msg="Cannot connect to %s API" % plugin.type)

        if request.if_modified_since:
            req_modified = request.if_modified_since
            script_modified = pytz.utc.localize(revision.created_at)
            if req_modified == script_modified:
                return redirect(code=304)

        response.last_modified = revision.created_at.strftime('%c')
        response.cache_control.private = True
        response.cache_control.max_age = 1

        body, lang, args = parser.parse_content(revision.content)

        atts = []
        options = {}
        timeout = 0
        if args:
            for arg, vals in args.items():
                if arg == 'attach':
                    atts.extend([dict(path=scr_name) for scr_name in vals])
                elif arg == 'timeout':
                    try:
                        timeout = int(vals[0])
                    except:
                        pass
                else:
                    options[arg] = vals

        section = dict(content=parser.remove_shebangs(body.strip()),
                       lang=lang,
                       attachments=atts,
                       timeout=timeout)
        data.append(section)
        revisions = sorted([r.serialize(
            skip=['id', 'script_id', 'draft', 'content'],
            rel=[("created_at", "created_at", lambda d: d)])
            for r in script.history
            if not r.draft], key=lambda r: r["created_at"], reverse=True)

        return O.workflow(rev=revision.version, sections=data,
                          revisions=revisions, editable=editable)

    @workflow.when(method='POST', template='json')
    @workflow.wrap_create(model_name='Workflow')
    def create(self, *args, **kwargs):
        if not args:
            return O.error(msg="Path not provided")

        workflow = request.json['workflow']

        content = flatten_workflow(workflow)
        path = '/'.join(args)
        full_path, _, name = path.rpartition('/')
        if not Script.valid_name(name):
            return O.error(msg="Invalid script name")

        repo, _, folder_path = full_path.partition('/')
        if not folder_path.startswith('/'):
            folder_path = "/" + folder_path
        if folder_path != '/':
            folder_path = folder_path + "/"
        folder = Folder.editable(request, repo, folder_path).first()
        if not folder:
            return O.error(msg="Folder not found")
        script = Script(name=name,
                        mime_type='text/workflow',
                        owner_id=request.user.id,
                        folder=folder)
        request.db.add(script)
        request.db.commit()
        request._model_id = script.id

        rev = Revision(content='\n'.join(content), script_id=script.id)
        request.db.add(rev)

    @workflow.when(method='PATCH', template='json')
    @workflow.wrap_update(model_name='Workflow')
    def preview(self, *args, **kwargs):
        if not args:
            return O.error(msg="Path not provided")
        expand = kwargs.get('expand') in ['1', 'true', 'True', 'on']
        workflow = request.json['workflow']

        new_content = flatten_workflow(workflow, expand=expand)
        path = '/'.join(args)

        return O.script(path=path, content="\n".join(new_content))

    @workflow.when(method='PUT', template='json')
    @workflow.wrap_update(model_name='Workflow')
    def save(self, *args, **kwargs):
        if not args:
            return O.error(msg="Path not provided")
        if not request.json:
            return O.error(msg="Data not provided")

        workflow = request.json['workflow']

        new_content = flatten_workflow(workflow)
        path = '/'.join(args)
        script = Script.find(request, path).one()
        new_name = workflow.get('new_name')
        if new_name:
            if not Script.valid_name(new_name):
                return O.error(msg="Invalid script name")
            script.name = new_name
        rev = Revision(content='\n'.join(new_content), script_id=script.id)
        request.db.add(rev)


def flatten_workflow(workflow, expand=False):
    new_content = []
    for section in workflow['sections']:
        timeout = section['timeout'] or ''
        lang = section.get('lang')
        shebang_lang = ""
        if lang and lang != 'bash':
            shebang_lang = "#! /usr/bin/%s" % lang
        if timeout:
            timeout = '--timeout=%s' % timeout
        subst = None
        if expand:
            subst = partial(include_substitute, request)
            content = section['content'].strip()
            parts = [parser.substitute_includes(content, callback=subst)]
        else:
            parts = [section['content'].strip()]
        if shebang_lang:
            new_content.append(shebang_lang)
        new_content.extend(parts)
    return new_content
