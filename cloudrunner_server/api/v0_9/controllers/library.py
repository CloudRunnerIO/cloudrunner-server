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
import pytz

from pecan import expose, request, response, redirect
from pecan.hooks import HookController

from cloudrunner.core.parser import parse_sections
from cloudrunner_server.api.decorators import wrap_command
from cloudrunner_server.api.hooks.error_hook import ErrorHook
from cloudrunner_server.api.hooks.db_hook import DbHook
from cloudrunner_server.api.hooks.perm_hook import PermHook
from cloudrunner_server.api.hooks.signal_hook import SignalHook
from cloudrunner_server.api.util import (JsonOutput as O, flatten_params)
from cloudrunner_server.api.model import (Repository, Script, Folder, Revision,
                                          RepositoryCreds, Org)
from cloudrunner_server.plugins.repository.base import PluginRepoBase
from cloudrunner_server.triggers.manager import TriggerManager

LOG = logging.getLogger()
AVAILABLE_REPO_TYPES = set(['cloudrunner', 'github', 'bitbucket', 'dropbox'])


class Library(HookController):

    __hooks__ = [DbHook(), ErrorHook(), SignalHook(),
                 PermHook(dont_have=set(['is_super_admin']))]

    @expose('json', generic=True)
    @wrap_command(Repository)
    def repo(self, *args, **kwargs):
        if not args:
            repos = Repository.visible(request).all()
            return O._anon(repositories=sorted([r.serialize(
                skip=['id', 'org_id', 'owner_id'],
                rel=[('owner.username', 'owner')]) for r in repos],
                key=lambda l: l['name']),
                quota=dict(total=request.tier.total_repos,
                           user=request.tier.total_repos,
                           external=request.tier.external_repos == "True"))
        else:
            repo_name = args[0]
            repo = Repository.visible(request).filter(
                Repository.name == repo_name).first()
            if repo.type == 'cloudrunner' or not repo.editable(request):
                return O.repository(repo.serialize(
                    skip=['id', 'org_id', 'owner_id'],
                    rel=[('owner.username', 'owner')]))
            else:
                return O.repository(repo.serialize(
                    skip=['id', 'org_id', 'owner_id'],
                    rel=[('owner.username', 'owner'),
                         ('credentials.auth_user', 'key'),
                         ('credentials.auth_pass', 'secret')]))

    @expose('json')
    def repo_plugins(self, *args, **kwargs):
        return O.plugins(_list=['cloudrunner'] +
                         [p.type for p in PluginRepoBase.__subclasses__()])

    @repo.when(method='POST', template='json')
    @repo.wrap_create()
    def repository_create(self, name=None, **kwargs):
        private = (bool(kwargs.get('private'))
                   and not kwargs.get('private') in ['0', 'false', 'False'])
        _type = kwargs.get('type')
        if _type not in (AVAILABLE_REPO_TYPES):
            return O.error(msg="Repo type [%s] not available" % _type)

        org = request.db.query(Org).filter(
            Org.name == request.user.org).one()
        repository = Repository(name=name, private=private,
                                type=_type,
                                owner_id=request.user.id,
                                org=org)
        request.db.add(repository)
        if _type != 'cloudrunner':
            key = kwargs.get('key')
            secret = kwargs.get('secret')
            creds = RepositoryCreds(provider=_type, auth_user=key,
                                    auth_pass=secret, repository=repository)
            request.db.add(creds)
        # Create root folder for repo
        root = Folder(name="/", full_name="/", repository=repository,
                      owner_id=request.user.id)
        request.db.add(root)

    @repo.when(method='PUT', template='json')
    @repo.wrap_update()
    def repository_update(self, name=None, **kwargs):
        new_name = kwargs.get('new_name')
        private = (bool(kwargs.get('private'))
                   and not kwargs.get('private') in ['0', 'false', 'False'])
        repository = Repository.own(request).filter(
            Repository.name == name).one()
        if new_name:
            repository.name = new_name
        repository.private = private
        if repository.type != 'cloudrunner':
            key = kwargs.get('key')
            secret = kwargs.get('secret')
            if secret:
                repository.credentials.auth_user = key
                repository.credentials.auth_pass = secret

        request.db.add(repository)

    @repo.when(method='DELETE', template='json')
    @repo.wrap_delete()
    def repository_delete(self, *args, **kwargs):
        name = args[0]
        repository = Repository.own(request).filter(
            Repository.name == name).one()
        if any([f for f in repository.folders
                if f.name != "/" or f.full_name != "/"]):
            return O.error(msg="Cannot remove repo, "
                           "not empty")
        for f in repository.folders:
            request.db.delete(f)
        request.db.delete(repository)

    @expose('json')
    def browse(self, repository, *args, **kwargs):
        if not repository:
            return O.error(msg="No repo selected")
        args = list([a for a in args if a])
        name = '/'
        if args:
            args.insert(0, '')
            name = "/".join(args)
            if not name.endswith('/'):
                name = name + "/"

        parent, _, __ = name.rstrip("/").rpartition("/")
        if parent:
            parent = parent + "/"
        else:
            parent = None
        repo = Repository.visible(request).filter(
            Repository.name == repository).first()
        if not repo:
            return O.error(msg="Repo not found")
        # if repo.type != 'cloudrunner':
        #   return O.error(msg="External repos are not browsable")

        folder = Folder.visible(request, repository, parent=parent).filter(
            Folder.full_name == name)
        folder = folder.one()

        subfolders = Folder.visible(
            request, repository, parent=name).all()
        scripts = request.db.query(Script).join(Folder).join(Revision)

        show_versions = (bool(kwargs.get('show_versions'))
                         and not kwargs.get('show_versions')
                         in ['0', 'false', 'False'])

        scripts = scripts.filter(
            Script.folder == folder,
            Folder.full_name == name).all()

        folders = [f.serialize(
            skip=['repository_id', 'parent_id', 'owner_id'],
            rel=[('owner.username', 'owner')]) for f in subfolders]

        def order(lst):
            return [r.version for r in sorted([item for item in lst],
                                              key=lambda x: x.created_at,
                                              reverse=True)
                    if not r.draft][-20:]  # last 20 versions

        def rev(lst):
            return [r.version for r in sorted([item for item in lst],
                                              key=lambda x: x.created_at,
                                              reverse=True)
                    if not r.draft][0]

        rels = [('owner.username', 'owner'), ('history', 'version', rev)]
        if show_versions:
            rels.append(('history', 'versions', order))
        scripts = sorted([s.serialize(skip=['folder_id', 'owner_id'],
                                      rel=rels)
                          for s in scripts],
                         key=lambda s: (s['mime_type'], s['name']))
        return O.contents(folders=folders, scripts=scripts,
                          owner=folder.owner.username)

    @expose('json')
    @wrap_command(Script)
    def revisions(self, repository, *args, **kwargs):
        path = "/".join(args)
        path.rstrip("/")
        if not path.startswith("/"):
            path = "/" + path

        path, _, script = path.rpartition('/')
        path = path + '/'

        scr = Script.visible(request,
                             repository,
                             path).filter(Script.name == script).first()
        if not scr:
            return O.error(msg="Script not found")

        return O.history(
            script=scr.name,
            owner=scr.owner.username,
            revisions=[r.serialize(
                       skip=['id', 'script_id', 'draft', 'content'])
                       for r in scr.history
                       if not r.draft])

    @expose('json', generic=True)
    @wrap_command(Script)
    def script(self, repository, *args, **kwargs):
        path = "/".join(args)
        path.rstrip("/")
        if not path.startswith("/"):
            path = "/" + path

        path, _, script = path.rpartition('/')
        path = path + '/'

        scr = Script.visible(request,
                             repository,
                             path).filter(Script.name == script).first()
        if scr:
            rev = scr.contents(request, **kwargs)
            if rev:
                if request.if_modified_since:
                    req_modified = request.if_modified_since
                    script_modified = pytz.utc.localize(rev.created_at)
                    if req_modified == script_modified:
                        return redirect(code=304)
                else:
                    response.last_modified = rev.created_at.strftime('%c')
                    response.cache_control.private = True
                    response.cache_control.max_age = 1
            return O.script(name=scr.name,
                            created_at=scr.created_at,
                            owner=scr.owner.username,
                            content=rev.content,
                            version=rev.version,
                            allow_sudo=scr.allow_sudo,
                            mime=scr.mime_type)
        else:
            return O.error(msg="Not found")
        return O.script({})

    @script.when(method='POST', template='json')
    @script.wrap_create()
    def script_create(self, name=None, **kwargs):
        name = name or kwargs['name']
        if not Script.valid_name(name):
            return O.error(msg="Invalid script name")
        content = kwargs['content']
        if parse_sections(content):
            mime = 'text/workflow'
        else:
            mime = 'text/plain'
        folder_name = kwargs['folder']
        repository, _, folder_path = folder_name.partition("/")
        folder_path = "/" + folder_path
        if not folder_path.endswith('/'):
            folder_path += "/"

        folder = Folder.editable(request, repository, folder_path).first()
        if not folder:
            return O.error(msg="Folder %s is not accessible" % folder_name)
        scr = Script(name=name,
                     owner_id=request.user.id,
                     folder=folder,
                     mime_type=mime)
        request.db.add(scr)
        request.db.commit()
        request._model_id = scr.id
        rev = Revision(content=content, script_id=scr.id)
        request.db.add(rev)

    @script.when(method='PUT', template='json')
    @script.wrap_modify()
    def script_update(self, name=None, **kwargs):
        name = name or kwargs['name']
        content = kwargs['content']
        folder_name = kwargs['folder']
        repository, _, folder_path = folder_name.partition("/")
        folder_path = "/" + folder_path
        if not folder_path.endswith('/'):
            folder_path += "/"

        scr = Script.visible(request,
                             repository,
                             folder_path).filter(
                                 Script.name == name).first()
        if not scr:
            return O.error(msg="Script '%s' not found" % name)

        if kwargs.get('new_name'):
            if not Script.valid_name(kwargs['new_name']):
                return O.error(msg="Invalid script name")
            scr.name = kwargs['new_name']

        if parse_sections(content):
            scr.mime_type = 'text/workflow'
        else:
            scr.mime_type = 'text/plain'

        request.db.add(scr)
        request.db.commit()

        request._model_id = scr.id
        rev = Revision(content=content, script_id=scr.id)
        request.db.add(rev)

    @script.when(method='PATCH', template='json')
    def script_patch(self, name=None, **kwargs):
        return self.script_update(name, **kwargs)

    @script.when(method='DELETE', template='json')
    @script.wrap_delete()
    def script_delete(self, *args, **kwargs):
        full_path = "/".join(args).strip("/")
        folder_name, _, name = full_path.rpartition("/")
        repository, _, folder_path = folder_name.partition("/")
        folder_path = "/" + folder_path
        if not folder_path.endswith('/'):
            folder_path += "/"

        scr = Script.visible(request,
                             repository,
                             folder_path).filter(
                                 Script.name == name).first()
        if not scr:
            return O.error(msg="Script '%s' not found" % name)
        request.db.delete(scr)

    @expose('json', generic=True)
    @wrap_command(Script, method='execute')
    def run(self, repository, *args, **kwargs):
        path = "/".join(args)
        path.strip("/")

        path, _, script = path.rpartition('/')

        script, _, rev = script.rpartition('@')
        if not script:
            script = rev
            rev = None

        env = flatten_params(request.params)
        full_path = "/".join([repository, path, script])
        if rev:
            full_path = "%s@%s" % (full_path, rev)
        man = TriggerManager()
        res = man.execute(user_id=request.user.id,
                          script_name=full_path,
                          job=None,
                          env=env, **kwargs)

        return O.result(**res)

    @expose('json', generic=True)
    @wrap_command(Folder)
    def folder(self, repository, *args, **kwargs):

        path = "/".join(args)
        return O.folder(name=path, repository=repository)

    @folder.when(method='POST', template='json')
    @folder.wrap_create()
    def folder_create(self, name=None, **kwargs):
        name = name or kwargs['name']
        parent_name = kwargs['folder'].lstrip('/')
        repository, _, folder_path = parent_name.partition("/")
        folder_path = "/" + folder_path
        if not folder_path.endswith('/'):
            folder_path += "/"

        parent = Folder.editable(request, repository, folder_path).first()
        if not parent:
            return O.error(msg="Parent folder '%s' is not accessible" %
                           folder_path)
        folder = Folder(name=name, repository=parent.repository,
                        owner_id=request.user.id,
                        parent=parent,
                        full_name="%s%s/" % (parent.full_name, name))
        request.db.add(folder)

    @folder.when(method='DELETE', template='json')
    @folder.wrap_delete()
    def folder_delete(self, *args, **kwargs):
        full_path = "/".join(args).strip("/")
        repository, _, folder_path = full_path.partition("/")
        folder_path = "/" + folder_path
        if not folder_path.endswith('/'):
            folder_path += "/"

        if folder_path == "/":
            print O.error(msg="Cannot delete root folder")
            return O.error(msg="Cannot delete root folder")

        folder = Folder.editable(request,
                                 repository,
                                 folder_path).first()
        if not folder:
            return O.error(msg="Folder '%s' not found" % full_path)
        request.db.delete(folder)
