import logging
from cloudrunner.core import parser

from pecan import expose, request
from pecan.hooks import HookController
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

from cloudrunner_server.api.hooks.error_hook import ErrorHook
from cloudrunner_server.api.hooks.db_hook import DbHook
from cloudrunner_server.api.hooks.perm_hook import PermHook
from cloudrunner_server.api.hooks.signal_hook import SignalHook, signal
from cloudrunner_server.api.util import JsonOutput as O
from cloudrunner_server.api.model import (Library as Lib, Script, User, Folder,
                                          LibraryCreds, Org)

LOG = logging.getLogger()


class Library(HookController):

    __hooks__ = [DbHook(), ErrorHook(), SignalHook(),
                 PermHook(dont_have={'is_super_admin'})]

    @expose('json', generic=True)
    def repo(self, *args, **kwargs):
        libs = Lib.visible(request).all()
        return O.libraries(_list=sorted([lib.serialize(
            skip=['id', 'org_id', 'owner_id'],
            rel=[('owner.username', 'owner')]) for lib in libs]),
            key=lambda l: l['name'])

    @repo.when(method='POST', template='json')
    @signal('library.repo', 'add',
            when=lambda x: x.get('success', {}).get("status") == "ok")
    def library_create(self, name=None, **kwargs):
        try:
            name = name or kwargs['name']
            private = bool(kwargs.get('private'))
            org = request.db.query(Org).filter(
                Org.name == request.user.org).one()
            library = Lib(name=name, private=private,
                          owner_id=request.user.id,
                          org=org)
            request.db.add(library)
            # Create root folder for repo
            root = Folder(name="/", full_name="/", library=library,
                          owner_id=request.user.id)
            request.db.add(root)
            request.db.commit()
            return O.success(status='ok')
        except KeyError, kex:
            return O.error(msg='Value not present: %s' % kex, field=str(kex))
        except IntegrityError:
            request.db.rollback()
            return O.error("Repo with this name already exists")
        except Exception, ex:
            request.db.rollback()
            return O.error(msg='%r' % ex)

    @repo.when(method='PUT', template='json')
    @signal('library.repo', 'update',
            when=lambda x: x.get('success', {}).get("status") == "ok")
    def library_update(self, name=None, **kwargs):
        try:
            new_name = kwargs['name']
            private = bool(kwargs['private'])
            library = Lib.visible(request).filter(Lib.name == name).one()
            library.name = new_name
            library.private = private
            request.db.add(library)
            request.db.commit()
            return O.success(status='ok')
        except KeyError, kex:
            return O.error(msg='Value not present: %s' % kex, field=str(kex))
        except Exception, ex:
            request.db.rollback()
            return O.error(msg='%r' % ex)

    @repo.when(method='DELETE', template='json')
    @signal('library.repo', 'delete',
            when=lambda x: x.get('success', {}).get("status") == "ok")
    def library_delete(self, *args, **kwargs):
        try:
            name = args[0]
            library = Lib.visible(request).filter(Lib.name == name).one()
            for folder in library.folders:
                if folder.name != "/" or folder.full_name != "/":
                    return O.error("Cannot remove repo, "
                                   "not empty")
                request.db.delete(folder)
            request.db.delete(library)
            request.db.commit()
            return O.success(status='ok')
        except KeyError, kex:
            return O.error(msg='Value not present: %s' % kex, field=str(kex))
        except IntegrityError:
            request.db.rollback()
            return O.error("Cannot remove repo, "
                           "probably not empty")
        except Exception, ex:
            request.db.rollback()
            return O.error(msg='%r' % ex)

    @expose('json')
    def browse(self, library, *args, **kwargs):
        if not library:
            return O.error("No repo selected")
        args = list([a for a in args if a])
        name = '/'
        if args:
            args.insert(0, '')
            name = "/".join(args)
            if not name.endswith('/'):
                name = name + "/"

        subfolders = Folder.visible(
            request, library, parent=name).all()
        scripts = request.db.query(Script).join(Folder, Lib).filter(
            Lib.name == library,
            Folder.full_name == name).all()

        folders = [f.serialize(
            skip=['library_id', 'parent_id', 'owner_id'],
            rel=[('owner.username', 'owner')]) for f in subfolders]

        scripts = sorted([s.serialize(skip=['folder_id', 'owner_id'],
                                      rel=[('owner.username', 'owner')])
                          for s in scripts],
                         key=lambda s: (s['mime_type'], s['name']))
        return O.contents(folders=folders, scripts=scripts)

    @expose('json', generic=True)
    def script(self, library, *args, **kwargs):

        path = "/".join(args)
        path.rstrip("/")
        if not path.startswith("/"):
            path = "/" + path

        path, _, script = path.rpartition('/')
        path = path + '/'

        scr = Script.visible(request,
                             library,
                             path).filter(Script.name == script).first()
        if scr:
            return O.script(name=scr.name,
                            created_at=scr.created_at,
                            owner=scr.owner.username,
                            content=scr.content,
                            mime=scr.mime_type)
        else:
            return O.error("Not found")
        return O.script({})

    @script.when(method='POST', template='json')
    @signal('library.scripts', 'add',
            when=lambda x: x.get('success', {}).get("status") == "ok")
    def script_create(self, name=None, **kwargs):
        try:
            name = name or kwargs['name']
            content = kwargs['content']
            mime = kwargs.get('mime', 'text/plain')
            folder_name = kwargs['folder']
            library, _, folder_path = folder_name.partition("/")
            folder_path = "/" + folder_path
            if not folder_path.endswith('/'):
                folder_path += "/"

            folder = Folder.editable(request, library, folder_path).first()
            if not folder:
                return O.error(msg="Folder %s is not accessible" % folder_name)
            scr = Script(name=name, content=content,
                         owner_id=request.user.id,
                         folder=folder,
                         mime_type=mime)
            request.db.add(scr)
            request.db.commit()
            return O.success(status='ok')
        except KeyError, kex:
            return O.error(msg='Value not present: %s' % kex, field=str(kex))
        except Exception, ex:
            request.db.rollback()
            return O.error(msg='%r' % ex)

    @script.when(method='PUT', template='json')
    @signal('library.scripts', 'update',
            when=lambda x: x.get('success', {}).get("status") == "ok")
    def script_update(self, name=None, **kwargs):
        try:
            name = name or kwargs['name']
            content = kwargs['content']
            mime = kwargs.get('mime', 'text/plain')
            folder_name = kwargs['folder']
            library, _, folder_path = folder_name.partition("/")
            folder_path = "/" + folder_path
            if not folder_path.endswith('/'):
                folder_path += "/"

            scr = Script.visible(request,
                                 library,
                                 folder_path).filter(
                                     Script.name == name).first()
            if not scr:
                return O.error(msg="Script '%s' not found" % name)

            scr.content = content
            scr.mime_type = mime
            request.db.add(scr)
            request.db.commit()
            return O.success(status='ok')
        except KeyError, kex:
            return O.error(msg='Value not present: %s' % kex, field=str(kex))
        except Exception, ex:
            LOG.exception(ex)
            request.db.rollback()
            return O.error(msg='%r' % ex)

    @script.when(method='PATCH', template='json')
    def script_patch(self, name=None, **kwargs):
        return self.script_update(name, **kwargs)

    @script.when(method='DELETE', template='json')
    @signal('library.scripts', 'delete',
            when=lambda x: x.get('success', {}).get("status") == "ok")
    def script_delete(self, *args, **kwargs):
        try:
            full_path = "/".join(args).strip("/")
            folder_name, _, name = full_path.rpartition("/")
            library, _, folder_path = folder_name.partition("/")
            folder_path = "/" + folder_path
            if not folder_path.endswith('/'):
                folder_path += "/"

            scr = Script.visible(request,
                                 library,
                                 folder_path).filter(
                                     Script.name == name).first()
            if not scr:
                return O.error(msg="Script '%s' not found" % name)
            request.db.delete(scr)
            request.db.commit()
            return O.success(status='ok')
        except KeyError, kex:
            return O.error(msg='Value not present: %s' % kex)
        except IntegrityError:
            request.db.rollback()
            return O.error("Cannot remove script, "
                           "as it is currently used by a trigger")
        except Exception, ex:
            LOG.exception(ex)
            request.db.rollback()
            return O.error(msg='%r' % ex)

    @expose('json', generic=True)
    def folder(self, library, *args, **kwargs):

        path = "/".join(args)
        return O.folder(name=path, library=library)

    @folder.when(method='POST', template='json')
    @signal('library.folder', 'add',
            when=lambda x: x.get('success', {}).get("status") == "ok")
    def folder_create(self, name=None, **kwargs):
        try:
            name = name or kwargs['name']
            parent_name = kwargs['folder'].lstrip('/')
            library, _, folder_path = parent_name.partition("/")
            folder_path = "/" + folder_path
            if not folder_path.endswith('/'):
                folder_path += "/"

            parent = Folder.editable(request, library, folder_path).first()
            if not parent:
                return O.error(msg="Parent folder '%s' is not accessible" %
                               folder_path)
            folder = Folder(name=name, library=parent.library,
                            owner_id=request.user.id,
                            parent=parent,
                            full_name="%s%s/" % (parent.full_name, name))
            request.db.add(folder)
            request.db.commit()
            return O.success(status='ok')
        except KeyError, kex:
            return O.error(msg='Value not present: %s' % kex, field=str(kex))
        except IntegrityError:
            request.db.rollback()
            return O.error("Cannot add folder, check name")
        except Exception, ex:
            request.db.rollback()
            return O.error(msg='%r' % ex)

    @folder.when(method='DELETE', template='json')
    @signal('library.folder', 'delete',
            when=lambda x: x.get('success', {}).get("status") == "ok")
    def folder_delete(self, *args, **kwargs):
        try:
            full_path = "/".join(args).strip("/")
            library, _, folder_path = full_path.partition("/")
            folder_path = "/" + folder_path
            if not folder_path.endswith('/'):
                folder_path += "/"

            folder = Folder.editable(request,
                                     library,
                                     folder_path).first()
            if not folder:
                return O.error(msg="Folder '%s' not found" % name)
            request.db.delete(folder)
            request.db.commit()
            return O.success(status='ok')
        except KeyError, kex:
            return O.error(msg='Value not present: %s' % kex)
        except IntegrityError:
            request.db.rollback()
            return O.error("Cannot remove folder, "
                           "probably not empty")
        except Exception, ex:
            LOG.exception(ex)
            request.db.rollback()
            return O.error(msg='%r' % ex)
