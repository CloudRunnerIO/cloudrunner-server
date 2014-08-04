from pecan import expose, request
from pecan.hooks import HookController
from sqlalchemy import or_

from cloudrunner_server.api.hooks.error_hook import ErrorHook
from cloudrunner_server.api.hooks.db_hook import DbHook
from cloudrunner_server.api.hooks.signal_hook import SignalHook, signal
from cloudrunner_server.api.util import JsonOutput as O
from cloudrunner_server.api.model import Workflow, Inline, User, Store, Org


class Library(HookController):

    __hooks__ = [DbHook(), ErrorHook(), SignalHook()]

    @expose('json', generic=True)
    def workflows(self, *args, **kwargs):
        if args:
            name = "/".join(args).rstrip("/")
            wf = request.db.query(Workflow).join(
                User, Org, Store).filter(
                    Workflow.name == name,
                    Org.name == request.user.org,
                    Store.store_type == 'local',
                    or_(User.username == request.user.username,
                        Workflow.private == None,  # noqa
                        Workflow.private == False,  # noqa
                        )).first()
            if wf:
                return O.workflow(name=wf.name,
                                  created_at=wf.created_at,
                                  owner=wf.owner.username,
                                  visibility='private'
                                  if wf.private else 'public',
                                  content=wf.content)
            else:
                return O.error("Not found")
        else:
            stores = request.db.query(Store).all()
            workflows = {}
            for store in stores:

                _wf = request.db.query(
                    Workflow.name,
                    Workflow.created_at,
                    Workflow.private,
                    User.username).join(
                        User, Store, Org).filter(
                            Org.name == request.user.org,
                            Store.id == store.id).filter(
                                or_(Workflow.private == None,  # noqa
                                    Workflow.private == False,  # noqa
                                    User.id == request.user.id)).order_by(
                            Workflow.name).all()

                workflows[store.name] = [dict(name=wf[0],
                                              created_at=wf[1],
                                              visibility='private' if wf[2]
                                              else 'public',
                                              owner=wf[3])
                                         for wf in _wf]
            return O.workflows(workflows)
        return O.workflows({})

    @workflows.when(method='POST', template='json')
    @signal('library.workflows', 'add',
            when=lambda x: x.get("status") == "ok")
    def workflow_create(self, name=None, **kwargs):
        try:
            name = name or kwargs['name']
            content = kwargs['content']
            private = bool(kwargs.get('private'))
            store = request.db.query(Store).filter(
                Store.store_type == 'local').first()
            wf = Workflow(name=name, content=content, private=private,
                          owner_id=request.user.id, store=store)
            request.db.add(wf)
            request.db.commit()
            return O.status('ok')
        except KeyError, kex:
            return O.error('Value not present: %s' % kex)
        except Exception, ex:
            request.db.rollback()
            return O.error('%r' % ex)

    @workflows.when(method='PUT', template='json')
    @signal('library.workflows', 'update',
            when=lambda x: x.get("status") == "ok")
    def workflow_update(self, name=None, **kwargs):
        try:
            content = kwargs['content']
            store = request.db.query(Store).filter(
                Store.store_type == 'local').first()
            if not store:
                return dict(error="Local store not found!")

            wf = request.db.query(Workflow).join(User).filter(
                Store.id == store.id,
                Workflow.name == name,
                User.id == request.user.id).first()
            if wf:
                wf.content = content
                request.db.add(wf)
                request.db.commit()
                return O.status('ok')
            else:
                return dict(error='Workflow not found!')
        except KeyError, kex:
            return dict(error='Value not present: %s' % kex)
        except Exception, ex:
            return dict(error='%r' % ex)

    @workflows.when(method='PATCH', template='json')
    def workflow_patch(self, name=None, **kwargs):
        return self.workflow_update(name, **kwargs)

    @workflows.when(method='DELETE', template='json')
    @signal('library.workflows', 'delete',
            when=lambda x: x.get("status") == "ok")
    def workflow_delete(self, *args, **kwargs):
        try:
            name = "/".join(args).rstrip("/")
            store = request.db.query(Store).filter(
                Store.store_type == 'local').first()
            if not store:
                return dict(error="Local store not found!")
            wf = request.db.query(Workflow).join(User).filter(
                Store.id == store.id,
                Workflow.name == name,
                User.id == request.user.id).first()
            if wf:
                request.db.delete(wf)
                return O.status('ok')
            else:
                return dict(error='Workflow not found!')
        except KeyError, kex:
            return dict(error='Value not present: %s' % kex)
        except Exception, ex:
            return dict(error='%r' % ex)

    # Inlines

    @expose('json', generic=True)
    def inlines(self, *args, **kwargs):
        inlines = []
        if args:
            name = "/".join(args).rstrip("/")
            inl = request.db.query(Inline).join(User, Org).filter(
                Org.name == request.user.org,
                Inline.name == name,
                or_(Inline.private == None,  # noqa
                    Inline.private == False,  # noqa
                    User.id == request.user.id)).first()
            if inl:
                return O.inline(name=inl.name,
                                owner=inl.owner.username,
                                visibility='private'
                                if inl.private else 'public',
                                content=inl.content)
            else:
                return dict(error="Not found")
        else:
            inlines = request.db.query(
                Inline.name, User.username, Inline.private).join(
                    User, Org).filter(
                        Org.name == request.user.org,
                        or_(Inline.private == None,  # noqa
                            Inline.private == False,  # noqa
                            User.id == request.user.id)).all()
            return O.inlines(_list=[
                dict(name=inl[0],
                     owner=inl[1],
                     visibility='private'
                                if inl[2] else 'public') for inl in inlines])

        return O.inlines(_list=inlines)

    @inlines.when(method='POST', template='json')
    @signal('library.inlines', 'add',
            when=lambda x: x.get("status") == "ok")
    def inline_create(self, name=None, **kwargs):
        try:
            name = name or kwargs['name']
            content = kwargs['content']
            private = bool(kwargs.get('private'))
            inl = Inline(name=name, content=content, private=private,
                         owner_id=request.user.id)
            request.db.add(inl)
            request.db.commit()
            return O.status('ok')
        except KeyError, kex:
            return dict(error='Value not present: %s' % kex)
        except Exception, ex:
            return dict(error='%r' % ex)

    @inlines.when(method='PUT', template='json')
    @signal('library.inlines', 'update',
            when=lambda x: x.get("status") == "ok")
    def inline_update(self, name=None, **kwargs):
        try:
            content = kwargs['content']

            inl = request.db.query(Inline).join(User).filter(
                Inline.name == name,
                User.id == request.user.id).first()
            if inl:
                inl.content = content
                request.db.add(inl)
                request.db.commit()
                return O.status('ok')
            else:
                return dict(error='Inline not found!')
        except KeyError, kex:
            return dict(error='Value not present: %s' % kex)
        except Exception, ex:
            return dict(error='%r' % ex)

    @inlines.when(method='PATCH', template='json')
    def inline_patch(self, name=None, **kwargs):
        return self.inline_update(name=name, **kwargs)

    @inlines.when(method='DELETE', template='json')
    @signal('library.inlines', 'delete',
            when=lambda x: x.get("status") == "ok")
    def inline_delete(self, *args, **kwargs):
        try:
            name = "/".join(args).rstrip("/")
            inl = request.db.query(Inline).join(User).filter(
                Inline.name == name,
                User.id == request.user.id).first()
            if inl:
                request.db.delete(inl)
                return O.status('ok')
            else:
                return dict(error='Inline not found!')
        except KeyError, kex:
            return dict(error='Value not present: %s' % kex)
        except Exception, ex:
            return dict(error='%r' % ex)
