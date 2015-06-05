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
import json
import logging
import re

try:
    from collections import OrderedDict
except ImportError:
    # python 2.6 or earlier, use backport
    from ordereddict import OrderedDict

from cloudrunner.core.parser import (parse_lang, substitute_includes,
                                     ParseError, DEFAULT_LANG)
from cloudrunner_server.api.model import Repository, Folder, Script, Revision
from cloudrunner_server.plugins.repository.base import (PluginRepoBase,
                                                        NotModified)

LOG = logging.getLogger()
ARGS = re.compile("(^#!\s*ARG\s+(?P<arg_k>[^=]+)=(?P<arg_v>.*)$)", re.M)


class DeploymentParser(object):

    def __init__(self, config, ctx):
        self.config = config
        self.steps = StepCollection(ctx, [])
        self.ctx = ctx
        self.env = {}

    def parse(self, deployment):
        if not isinstance(deployment.content, dict):
            self.content = json.loads(deployment.content)
        else:
            self.content = deployment.content
        self.name = deployment.name
        self.object = deployment
        if "env" in self.content:
            self.env = self.content.get('env', {})
        self.steps = StepCollection(self.ctx, self.content["steps"])


class StepCollection(list):

    def __init__(self, ctx, items):
        super(StepCollection, self).__init__()
        for item in items:
            self.append(Step(ctx, item))


class Step(object):

    def __init__(self, ctx, data):
        self.targets = data.get('target')
        self.raw_content = data.get('content')
        self.path = None
        self.body = None
        self.timeout = int(data.get('timeout', 0))
        self.env = json.loads(data.get('env', '{}'))
        self.args = None
        self.text = None
        self.lang = DEFAULT_LANG
        self.atts = []

        if isinstance(self.raw_content, dict):
            if "path" in self.raw_content:
                self.path = self.raw_content['path']
                repo, _dir, scr_name, rev = Script.parse(self.path)
                scr = Script.find(ctx, self.path).one()
                if not scr:
                    raise ParseError("Script '%s' not found" % self.path)
                revision = scr.contents(ctx, rev=rev)
                c = revision.content
                if revision.meta:
                    try:
                        meta = json.loads(revision.meta)
                        timeout = meta.get('timeout')
                        if timeout and int(timeout):
                            self.timeout = int(timeout)
                    except:
                        pass
            elif 'text' in self.raw_content:
                c = self.content['text']
            else:
                raise ParseError("Cannot find step body")

            scr_parse = ScriptParser()
            scr_parse.parse(ctx, c)
            self.body = scr_parse.body
            self.lang = scr_parse.lang
            self.args = scr_parse.args
            if self.args.timeout:
                self.timeout = self.args.timeout[0]
            if self.args.attach:
                self.atts = self.args.attach


class ArgsCollection(object):

    def __init__(self, *args, **kwargs):
        self._items = OrderedDict()
        for arg in args:
            k, _, v = arg.partition('=')
            k = k.lstrip('-')
            if not kwargs.get('flatten'):
                self._items.setdefault(k, []).append(v)
            else:
                self._items[k] = v

    def get(self, k, default=None):
        return self._items.get(k, default)

    def items(self):
        return self._items.items()

    def __getattr__(self, k, default=None):
        return self._items.get(k, default)

    def __contains__(self, k):
        return k in self._items

    def __getitem__(self, k):
        return self._items['k']


class ScriptParser(object):

    """
    Parses the contents of a script, substituting includes with actual code
    """

    def __init__(self):
        self.args = ArgsCollection()
        self.body = ''
        self.lang = DEFAULT_LANG

    def parse(self, ctx, content):
        try:
            args = []
            m_args = ARGS.findall(content)
            for match in m_args:
                args.append({match[1]: match[2]})
            args = ArgsCollection(*args)

            lang = parse_lang(content)
            subst = partial(include_substitute, ctx)
            self.body = substitute_includes(content, callback=subst)

            self.content = self.body
            self.lang = lang
        except Exception, exc:
            LOG.error(exc)
            raise ParseError("Error parsing script")


def include_substitute(ctx, path):
    try:
        scr = _parse_script_name(ctx, path)
    except Exception, ex:
        LOG.exception(ex)
        raise ParseError("Include file: '%s' not found" % path)
    else:
        if scr:
            return scr.content
    raise ParseError("Include file: '%s' not found" % path)


def _parse_script_name(ctx, path):

    repo_name, name, scr_, rev = Script.parse(path)
    full_path = "/".join([name, scr_])
    parent, _, __ = name.rstrip("/").rpartition("/")
    if parent:
        parent = parent + "/"
    else:
        parent = None

    repo = Repository.visible(ctx).filter(
        Repository.name == repo_name).one()

    if repo.linked:
        parent_repo = repo
        repo = repo.linked
        root_folder = ctx.db.query(Folder).filter(
            Folder.full_name == name, Folder.repository == repo).one()
    else:
        root_folder = Folder.visible(
            ctx, repo_name, parent=parent).filter(
                Folder.full_name == name).one()

    try:
        s = [sc for sc in root_folder.scripts if sc.name == scr_]
        if not s:
            LOG.error("Cannot find %s" % scr_)
            return None
        else:
            s = s[0]
        if rev:
            return s.contents(ctx, rev=rev)
    except:
        LOG.error("Cannot find %s" % scr_)
        raise
    if repo.type != 'cloudrunner':
        plugin = PluginRepoBase.find(repo.type)
        if not plugin:
            LOG.warn("No plugin found for repo %s" % (repo.type,))
            return None
        plugin = plugin(parent_repo.credentials.auth_user,
                        parent_repo.credentials.auth_pass,
                        parent_repo.credentials.auth_args)
        try:
            contents, last_modified, rev = plugin.contents(
                repo_name, full_path, rev=rev,
                last_modified=s.contents(ctx).created_at)
            exists = s.contents(ctx, rev=rev)
            if not exists:
                exists = Revision(created_at=last_modified,
                                  version=rev, script=s,
                                  content=contents)
            else:
                exists.content = contents
                exists.created_at = last_modified
            ctx.db.add(exists)

            ctx.db.commit()
            ctx.db.begin()
            return exists
        except NotModified:
            return s.contents(ctx)
    else:
        return s.contents(ctx)

    return None
