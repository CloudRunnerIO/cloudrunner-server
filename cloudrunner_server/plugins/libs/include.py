#!/usr/bin/python
# -*- coding: utf-8 -*-
# vim: tabstop=4 shiftwidth=4 softtabstop=4

# /*******************************************************
#  * Copyright (C) 2013-2014 CloudRunner.io <info@cloudrunner.io>
#  *
#  * Proprietary and confidential
#  * This file is part of CloudRunner Server.
#  *
#  * CloudRunner Server can not be copied and/or distributed without the express
#  * permission of CloudRunner.io
#  *******************************************************/

from datetime import datetime
import json
import logging
import os
import os.path as p
import re

from cloudrunner import LIB_DIR
from cloudrunner_server.plugins.args_provider import ArgsProvider
from cloudrunner_server.plugins.args_provider import CliArgsProvider
from cloudrunner_server.plugins.libs.base import IncludeLibPluginBase
from cloudrunner.util.http import parse_url
from cloudrunner.util.http import load_from_link

LOG = logging.getLogger(__name__)
PROTO_RE = re.compile(r'^(ht|f|sf)+tp[s]*://([^/]+/){1}')


def sanitize(lib):
    return PROTO_RE.sub('', lib)


def _default_dir():
    _def_dir = p.join(LIB_DIR, "cloudrunner", "plugins", "library")
    if not p.exists(_def_dir):
        os.makedirs(_def_dir)
    return _def_dir


class LibIncludePlugin(IncludeLibPluginBase, ArgsProvider, CliArgsProvider):

    def __init__(self):
        self.lib_dir = getattr(LibIncludePlugin, 'lib_dir', _default_dir())
        LOG.info("LIB plugin started with dir: %s" % self.lib_dir)
        if not p.exists(self.lib_dir):
            os.makedirs(self.lib_dir)

    def _system(self):
            system_lib_dir = p.join(self.lib_dir, '__system__')
            if not p.exists(system_lib_dir):
                os.makedirs(system_lib_dir)
            return system_lib_dir

    def _dir(self, is_public, user_org):
        if is_public:
            public_lib_dir = p.join(self.lib_dir, user_org[1],
                                    '__public__')
            if not p.exists(public_lib_dir):
                os.makedirs(public_lib_dir)
            return public_lib_dir
        else:
            user_lib_dir = p.join(self.lib_dir, user_org[1], user_org[0])
            if not p.exists(user_lib_dir):
                os.makedirs(user_lib_dir)
            return user_lib_dir

    def _append_path(self, lib_dir, name):
        try:
            lib_file = p.abspath(p.join(lib_dir, name))
            # check path
            base = p.relpath(lib_file, lib_dir)
            if base.startswith('..'):
                # outside bounds
                return None

            if not p.exists(p.dirname(lib_file)):
                os.makedirs(p.dirname(lib_file))
            return lib_file
        except:
            return None

    def append_args(self):
        return [dict(arg='--attach-lib', dest='attachlib', action='append'),
                dict(arg='--include-lib', dest='includelib', action='append'),
                dict(arg='--store-lib', dest='storelib')]

    def add(self, user_org, name, script, **kwargs):
        is_public = kwargs.get('is_public', False)
        _lib_dir = self._dir(is_public, user_org)

        lib_file = self._append_path(_lib_dir, name)
        if not lib_file:
            return False, "Invalid file name"

        if lib_file.endswith('.meta'):
            # Prevent .meta overwrite
            return False, "Invalid file name, cannot end with .meta"

        if p.exists(lib_file) and not kwargs.get('overwrite', False):
                return False, "Script already exists"

        LOG.info("Added new library script [%s] from [%s] with arguments: %s" %
                (name, user_org[0], kwargs))

        open(lib_file, 'w').write(script)
        meta = json.dumps(dict(owner=user_org[0],
                               created_at=datetime.strftime(datetime.now(),
                                                            '%s')))
        open(lib_file + '.meta', 'w').write(meta)

        return (True, 'OK')

    def show(self, user_org, name, **kwargs):
        proto_host = parse_url(name)
        if proto_host:
            return self._load_url(proto_host[0], proto_host[1], **kwargs)
        else:
            return self._load_local(user_org, name, **kwargs)

    def _load_url(self, proto_host, name,  **kwargs):
        reply, data = load_from_link(proto_host, name)
        return reply == 0, data

    def _load_local(self, user_org, name, **kwargs):
        is_public = kwargs.get('is_public', False)
        is_system = kwargs.get('is_system', False)
        if is_system:
            _lib_dir = self._system()
        else:
            _lib_dir = self._dir(is_public, user_org)

        lib_file = self._append_path(_lib_dir, name)
        if not lib_file:
            return False, "Invalid file name"

        if not is_public and not p.exists(lib_file):
            # try last resort to lookup in Public, if is_public is ommited
            _lib_dir = self._dir(True, user_org)
            lib_file = self._append_path(_lib_dir, name)

        if not is_public and not is_system and not p.exists(lib_file):
            # try last resort to lookup in Public, if is_public is ommited
            _lib_dir = self._system()
            lib_file = self._append_path(_lib_dir, name)

        if not p.exists(lib_file):
            return False, "#Script doesn't exist"

        return True, open(lib_file).read()

    def list(self, user_org, **kwargs):
        scripts = {}
        scripts['public'] = []
        scripts['private'] = []
        scripts['system'] = []

        # Private
        lib_path = self._dir(False, user_org)
        for (_dir, _, _files) in os.walk(lib_path):
            for _file in _files:
                if _file.endswith('.meta'):
                    continue
                try:
                    meta = json.loads(
                        open(p.join(_dir, _file) + '.meta').read())
                    owner = meta['owner']
                except:
                    owner = 'N/A'
                scripts['private'].append(dict(owner=owner,
                                               name=p.relpath(
                                                   p.join(_dir,
                                                          _file),
                                               lib_path)))
        # Public
        pub_dir = self._dir(True, user_org)
        for (_dir, _, _files) in os.walk(pub_dir):
            for _file in _files:
                if _file.endswith('.meta'):
                    continue
                try:
                    meta = json.loads(
                        open(p.join(_dir, _file) + '.meta').read())
                    owner = meta['owner']
                except:
                    owner = 'N/A'
                scripts['public'].append(dict(owner=owner,
                                              name=p.relpath(
                                                  p.join(_dir,
                                                         _file),
                                              pub_dir)))

        # System
        sys_dir = self._system()
        for (_dir, _, _files) in os.walk(sys_dir):
            for _file in _files:
                if _file.endswith('.meta'):
                    continue
                owner = 'system'
                scripts['system'].append(dict(owner=owner,
                                              name=p.relpath(
                                                  p.join(_dir,
                                                         _file),
                                              sys_dir)))

        return True, scripts

    def delete(self, user_org, name, **kwargs):
        is_public = kwargs.get('is_public', False)
        _lib_dir = self._dir(is_public, user_org)

        lib_file = p.join(_lib_dir, name)

        if not is_public and not p.exists(lib_file):
            # try last resort to lookup in Public, if is_public is ommited
            lib_file = p.join(self._dir(True, user_org), name)
            is_public = True

        if is_public:
            # Enforce check for ownership
            try:
                meta = json.loads(open(lib_file + '.meta').read())
                if meta['owner'] != user_org[0]:
                    return False, "Cannot delete public script from non-owner"
            except Exception, ex:
                LOG.warn("Meta data for script %s doesn't exist!" % name)

        LOG.info("Deleted library script [%s] from [%s]" %
                (name, user_org[0]))

        if not p.exists(lib_file):
            return False, "Script doesn't exist"

        os.unlink(lib_file)
        try:
            # Remove also meta
            os.unlink(lib_file + '.meta')
        except:
            pass
        return True, "Deleted"

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

        elif args.storelib:
            self.add(user_org, args.storelib, section)

    # CLI arguments
    def append_cli_args(self, arg_parser):
        lib_actions = arg_parser.add_subparsers(dest='action')

        list_ = lib_actions.add_parser('list', add_help=False,
                                       help="List library items")
        list_.add_argument('--json', action='store_true',
                           help='Return in JSON format')

        show = lib_actions.add_parser('show', add_help=False,
                                      help='Show a library item')
        show.add_argument('name', help='Library item name')
        show.add_argument('--public', help='Search in Public',
                          action='store_true')
        show.add_argument('--system', help='Search in System',
                          action='store_true')

        add = lib_actions.add_parser('add', add_help=False,
                                     help='Add new library item')
        add.add_argument('--overwrite', '-o', action='store_true',
                         help='Overwrite existing')
        add.add_argument('--private', help='Save as private',
                         action='store_true', default=False)
        add.add_argument('name', help='Item name')
        add.add_argument('content', help='Item content')

        delete = lib_actions.add_parser('delete', add_help=False,
                                        help='Delete a library item')
        delete.add_argument('name', help='Library item name')

        return "library"

    def call(self, user_org, data, ctx, args):
        if args.action == "list":
            rows = []
            success, items = self.list(user_org)
            if args.json:
                return success, items
            if success:
                if items['public']:
                    rows.append('PUBLIC')
                    for item in items['public']:
                        rows.append('%-40s%s' % (item['name'], item['owner']))
                if items['private']:
                    rows.append('PRIVATE')
                    for item in items['private']:
                        rows.append('%-40s%s' % (item['name'], item['owner']))
                if items['system']:
                    rows.append('SYSTEM')
                    for item in items['system']:
                        rows.append('%-40s%s' % (item['name'], item['owner']))

                return (True, '\n'.join(rows))
            return success, items
        elif args.action == 'add':
            return self.add(user_org, args.name, data,
                            overwrite=args.overwrite,
                            is_public=not args.private)

        elif args.action == 'show':
            return self.show(user_org, args.name,
                             is_public=args.public,
                             is_system=args.system)

        elif args.action == 'delete':
            return self.delete(user_org, args.name)
