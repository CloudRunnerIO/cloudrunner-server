from pecan import expose, request  # noqa
from pecan.hooks import HookController

from cloudrunner_server.api.hooks.db_hook import DbHook
from cloudrunner_server.api.hooks.error_hook import ErrorHook
from cloudrunner_server.api.hooks.user_hook import UserHook
from cloudrunner_server.api.hooks.signal_hook import SignalHook, signal
from cloudrunner_server.api.model import Group, Org, Role
from cloudrunner_server.api.util import JsonOutput as O


class Manage(HookController):

    __hooks__ = [UserHook(), DbHook(), SignalHook(), ErrorHook()]

    #
    # USERS ##########
    #

    @expose('json', generic=True)
    def users(self, *args, **kwargs):
        users = [dict(name=u[0],
                      email=u[1],
                      org=u[2],
                      groups=u[3])
                 for u in request.user_manager.list_users(request.user.org)]
        return O.users(_list=users)

    @users.when(method='POST', template='json')
    @signal('manage.users', 'create',
            when=lambda r: not r.get("error"))
    def create(self, username=None, password=None,
               email=None, org=None, **kwargs):
        username = username or kwargs['username']
        email = email or kwargs['email']
        password = password or kwargs['password']
        org = org or kwargs['org']
        success, msg = request.user_manager.create_user(username,
                                                        password,
                                                        email,
                                                        org)
        if success:
            return dict(status="ok")
        else:
            return dict(error=msg)

    @users.when(method='PUT', template='json')
    @signal('manage.users', 'update',
            when=lambda r: not r.get("error"))
    def update(self, **kwargs):
        try:
            username = kwargs['username']
            email = kwargs['email']
            password = kwargs['password']
            success, msg = request.user_manager.update_user(username,
                                                            password=password,
                                                            email=email)
            if success:
                return dict(status="ok")
            else:
                return dict(error=msg)
        except KeyError, kerr:
            return dict(error='Missing value: %s' % kerr)

    @users.when(method='PATCH', template='json')
    @signal('manage.users', 'update',
            when=lambda r: not r.get("error"))
    def patch(self, **kwargs):
        username = kwargs.pop('username')
        email = kwargs.get('email')
        password = kwargs.get('password')
        if not email and not password:
            return dict(error='Nothing to update')

        success, msg = request.user_manager.update_user(username,
                                                        password=password,
                                                        email=email)
        if success:
            return dict(status="ok")
        else:
            return dict(error=msg)

    @users.when(method='DELETE', template='json')
    @signal('manage.users', 'delete',
            when=lambda r: not r.get("error"))
    def delete(self, username, **kwargs):
        username = username
        success, msg = request.user_manager.remove_user(username)
        if success:
            return dict(status="ok")
        else:
            return dict(error=msg)

    #
    # ROLES ##########
    #

    @expose('json', generic=True)
    def roles(self, username, *args, **kwargs):
        roles = [dict(node=r[0], as_user=r[1]) for r in
                 request.user_manager.user_roles(username).items()]
        return O.roles(_list=roles)

    @roles.when(method='POST', template='json')
    @signal('manage.roles', 'create',
            when=lambda r: not r.get("error"))
    def add_role(self, username, *args, **kwargs):
        node = kwargs['node']
        role = kwargs['role']
        (success, msg) = request.user_manager.add_role(username, node, role)
        if success:
            return dict(status="ok")
        else:
            return dict(error=msg)

    @roles.when(method='DELETE', template='json')
    @signal('manage.roles', 'delete',
            when=lambda r: not r.get("error"))
    def rm_role(self, username, node, **kwargs):
        (success, msg) = request.user_manager.remove_role(username, node)
        if success:
            return dict(status="ok")
        else:
            return dict(error=msg)

    #
    # GROUPS ##########
    #

    @expose('json', generic=True)
    def groups(self, *args, **kwargs):
        def modifier(roles):
            return [dict(as_user=role.as_user, servers=role.servers)
                    for role in roles]

        groups = [g.serialize(skip=['id', 'org_id'],
                              rel=[("roles", 'roles', modifier)]) for g in
                  request.db.query(Group).join(Org).outerjoin(Role).filter(
                  Org.name == request.user.org).all()]
        return O.groups(_list=groups)

    @groups.when(method='POST', template='json')
    @signal('manage.groups', 'create',
            when=lambda r: not r.get("error"))
    def add_group(self, name, *args, **kwargs):
        name = name or kwargs['name']
        (success, msg) = request.user_manager.add_group(request.user.org, name)
        if success:
            return dict(status="ok")
        else:
            return dict(error=msg)

    @groups.when(method='PUT', template='json')
    @signal('manage.groups', 'update',
            when=lambda r: not r.get("error"))
    def modify_group_roles(self, name, *args, **kwargs):
        name = name or kwargs['name']
        mods = kwargs['modifications']
        assert isinstance(mods, dict)
        if mods.get("add"):
            assert isinstance(mods['add'], dict)
        if mods.get("remove"):
            assert isinstance(mods['remove'], dict)
        (success, msg) = request.user_manager.add_group_role(
            name, add=mods.get("add"), remove=mods.get("remove"))
        if success:
            return dict(status="ok")
        else:
            return dict(error=msg)

    @groups.when(method='DELETE', template='json')
    @signal('manage.groups', 'delete',
            when=lambda r: not r.get("error"))
    def rm_group(self, name, **kwargs):
        (success, msg) = request.user_manager.remove_group(request.user.org,
                                                           name)
        if success:
            return dict(status="ok")
        else:
            return dict(error=msg)

    #
    # ORGS ###########
    #

    @expose('json', generic=True)
    def orgs(self, *args, **kwargs):
        orgs = [dict(name=u[0], id=u[1], active=u[2]) for u in
                request.user_manager.list_orgs()]
        return O.orgs(_list=orgs)

    @orgs.when(method='POST', template='json')
    @signal('manage.orgs', 'create',
            when=lambda r: r.get("status") == 'ok')
    def create_org(self, **kwargs):
        org = kwargs['org']
        success, msg = request.user_manager.create_org(org)
        if success:
            return dict(status="ok")
        else:
            return dict(error=msg)

    @orgs.when(method='PATCH', template='json')
    @signal('manage.orgs', 'update',
            when=lambda r: r.get("status") == 'ok')
    def activate(self, org, **kwargs):
        action = kwargs['action']
        if action in ['0', 'false', 'False']:
            success, msg = request.user_manager.deactivate_org(org)
        elif action in ['1', 'true', 'True']:
            success, msg = request.user_manager.activate_org(org)
        else:
            success, msg = False, "Unknown command '%s'" % action

        if success:
            return dict(status="ok")
        else:
            return dict(error=msg)

    @orgs.when(method='DELETE', template='json')
    @signal('manage.orgs', 'delete',
            when=lambda r: r.get("status") == 'ok')
    def delete_org(self, org, **kwargs):
        success, msg = request.user_manager.remove_org(org)
        if success:
            return dict(status="ok")
        else:
            return dict(error=msg)
