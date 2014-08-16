from cloudrunner.core import parser

from pecan import expose, request
from pecan.hooks import HookController
from sqlalchemy import or_

from cloudrunner_server.api.hooks.error_hook import ErrorHook
from cloudrunner_server.api.hooks.db_hook import DbHook
from cloudrunner_server.api.hooks.signal_hook import SignalHook, signal
from cloudrunner_server.api.util import JsonOutput as O
from cloudrunner_server.api.model import Script, User, Store, Org


class Library(HookController):

    __hooks__ = [DbHook(), ErrorHook(), SignalHook()]

    @expose('json', generic=True)
    def scripts(self, *args, **kwargs):
        if args:
            name = "/".join(args).rstrip("/")
            scr = request.db.query(Script).join(
                User, Org, Store).filter(
                    Script.name == name,
                    Org.name == request.user.org,
                    Store.store_type == 'local',
                    or_(User.username == request.user.username,
                        Script.private == None,  # noqa
                        Script.private == False,  # noqa
                        )).first()
            if scr:
                return O.script(name=scr.name,
                                created_at=scr.created_at,
                                owner=scr.owner.username,
                                visibility='private'
                                if scr.private else 'public',
                                content=scr.content,
                                mime=scr.mime_type)
            else:
                return O.error("Not found")
        else:
            stores = request.db.query(Store).all()
            scripts = {}
            for store in stores:

                _scr = request.db.query(
                    Script.name,
                    Script.created_at,
                    Script.private,
                    User.username,
                    Script.mime_type).join(
                        User, Store, Org).filter(
                            Org.name == request.user.org,
                            Store.id == store.id).filter(
                                or_(Script.private == None,  # noqa
                                    Script.private == False,  # noqa
                                    User.id == request.user.id)).order_by(
                            Script.name).all()

                scripts[store.name] = [dict(name=scr[0],
                                            created_at=scr[1],
                                            visibility='private' if scr[2]
                                            else 'public',
                                            owner=scr[3],
                                            mime=scr[4])
                                       for scr in _scr]
            return O.scripts(scripts)
        return O.scripts({})

    @scripts.when(method='POST', template='json')
    @signal('library.scripts', 'add',
            when=lambda x: x.get("status") == "ok")
    def script_create(self, name=None, **kwargs):
        try:
            name = name or kwargs['name']
            content = kwargs['content']
            private = bool(kwargs.get('private'))
            store = request.db.query(Store).filter(
                Store.store_type == 'local').first()
            sections = parser.parse_sections(content)
            if sections:
                mime = 'text/workflow'
            else:
                mime = 'text/plain'
            scr = Script(name=name, content=content, private=private,
                         owner_id=request.user.id, store=store, mime_type=mime)
            request.db.add(scr)
            request.db.commit()
            return O.status('ok')
        except KeyError, kex:
            return O.error('Value not present: %s' % kex)
        except Exception, ex:
            request.db.rollback()
            return O.error('%r' % ex)

    @scripts.when(method='PUT', template='json')
    @signal('library.scripts', 'update',
            when=lambda x: x.get("status") == "ok")
    def script_update(self, name=None, **kwargs):
        try:
            content = kwargs['content']
            store = request.db.query(Store).filter(
                Store.store_type == 'local').first()
            if not store:
                return dict(error="Local store not found!")

            sections = parser.parse_sections(content)
            mime = None
            if sections:
                mime = 'text/workflow'

            scr = request.db.query(Script).join(User).filter(
                Store.id == store.id,
                Script.name == name,
                User.id == request.user.id).first()
            if scr:
                scr.content = content
                if mime:
                    scr.mime_type = mime
                request.db.add(scr)
                request.db.commit()
                return O.status('ok')
            else:
                return dict(error='Script not found!')
        except KeyError, kex:
            return dict(error='Value not present: %s' % kex)
        except Exception, ex:
            return dict(error='%r' % ex)

    @scripts.when(method='PATCH', template='json')
    def script_patch(self, name=None, **kwargs):
        return self.script_update(name, **kwargs)

    @scripts.when(method='DELETE', template='json')
    @signal('library.scripts', 'delete',
            when=lambda x: x.get("status") == "ok")
    def script_delete(self, *args, **kwargs):
        try:
            name = "/".join(args).rstrip("/")
            store = request.db.query(Store).filter(
                Store.store_type == 'local').first()
            if not store:
                return dict(error="Local store not found!")
            scr = request.db.query(Script).join(User).filter(
                Store.id == store.id,
                Script.name == name,
                User.id == request.user.id).first()
            if scr:
                request.db.delete(scr)
                return O.status('ok')
            else:
                return dict(error='Script not found!')
        except KeyError, kex:
            return dict(error='Value not present: %s' % kex)
        except Exception, ex:
            return dict(error='%r' % ex)
