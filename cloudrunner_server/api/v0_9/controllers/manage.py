import logging
from pecan import expose, request  # noqa
from pecan.hooks import HookController
from sqlalchemy.exc import IntegrityError

from cloudrunner_server.api.hooks.db_hook import DbHook
from cloudrunner_server.api.hooks.error_hook import ErrorHook
from cloudrunner_server.api.hooks.perm_hook import PermHook
from cloudrunner_server.api.hooks.user_hook import UserHook
from cloudrunner_server.api.hooks.signal_hook import SignalHook, signal
from cloudrunner_server.api.model import Group, Org, Role, User
from cloudrunner_server.api.util import JsonOutput as O
from cloudrunner_server.api.policy.decorators import check_policy

LOG = logging.getLogger()

USER_ATTR = {'username', 'email', 'first_name',
             'last_name', 'department', 'position'}


class Manage(HookController):

    __hooks__ = [UserHook(), DbHook(), SignalHook(), ErrorHook(),
                 PermHook(have={'is_admin'})]

    #
    # USERS ##########
    #

    @expose('json', generic=True)
    def users(self, name=None, **kwargs):
        if name:
            user = User.visible(request).filter(User.username == name).first()
            return O.user(user.serialize(
                skip=['id', 'org_id', 'password'],
                rel=[('groups.name', 'groups')]))
        else:
            users = [u.serialize(
                skip=['id', 'org_id', 'password'],
                rel=[('groups.name', 'groups')])
                for u in User.visible(request).all()]
            return O.users(_list=users)

    @users.when(method='POST', template='json')
    @signal('manage.users', 'create',
            when=lambda r: not r.get("error"))
    def create(self, username=None, **kwargs):
        try:
            username = username or kwargs['username']
            email = kwargs['email']
            password = kwargs['password']
            first_name = kwargs['first_name']
            last_name = kwargs['last_name']
            department = kwargs['department']
            position = kwargs['position']

            org = request.db.query(Org).filter(
                Org.name == request.user.org).one()
            new_user = User(username=username, email=email,
                            first_name=first_name, last_name=last_name,
                            department=department, position=position, org=org)
            new_user.set_password(password)
            request.db.add(new_user)
            request.db.commit()
            return O.success(status="ok")
        except KeyError, kerr:
            return O.error(msg="Field not present: '%s'" % kerr,
                           field=str(kerr))
        except IntegrityError:
            request.db.rollback()
            return O.error(msg="Username is already taken by another user",
                           field="username")
        except Exception, ex:
            LOG.exception(ex)
            request.db.rollback()
            return O.error(msg="Cannot create user")

    @users.when(method='PATCH', template='json')
    @signal('manage.users', 'update',
            when=lambda r: not r.get("error"))
    def patch(self, username=None, **kwargs):
        try:
            name = username
            user = User.visible(request).filter(User.username == name).first()
            if not user:
                return O.error(msg="User not found")

            for k in set(kwargs.keys()).intersection(USER_ATTR):
                setattr(user, k, kwargs[k])

            groups = request.POST.getall('groups')
            if groups:
                to_remove = [g for g in user.groups
                             if g.name not in groups]
                for g in to_remove:
                    user.groups.remove(g)
                grps = Group.visible(request).filter(
                    Group.name.in_(groups)).all()
                for g in grps:
                    user.groups.append(g)
            else:
                user.groups[:] = []
            password = kwargs.get('password')
            if password:
                user.set_password(password)
            request.db.add(user)
            request.db.commit()
            return O.success(status='ok')
        except KeyError, kerr:
            return O.error(msg="Field not present: %s" % kerr,
                           field=str(kerr))
        except Exception, ex:
            LOG.exception(ex)
            request.db.rollback()
            return O.error(msg="Cannot update user")

    @users.when(method='PUT', template='json')
    @signal('manage.users', 'update',
            when=lambda r: not r.get("error"))
    def update(self, **kwargs):
        try:
            # assert all values
            (kwargs['username'], kwargs['email'], kwargs['first_name'],
                kwargs['last_name'], kwargs['department'], kwargs['position'])
            return self.patch(**kwargs)
        except KeyError, kerr:
            return O.error(msg="Field not present: %s" % kerr,
                           field=str(kerr))

    @users.when(method='DELETE', template='json')
    @signal('manage.users', 'delete',
            when=lambda r: not r.get("error"))
    def delete(self, username, **kwargs):
        try:
            name = username
            user = User.visible(request).filter(User.username == name).first()
            if not user:
                return O.error(msg="User not found")

            request.db.delete(user)
            request.db.commit()
            return O.success(status='ok')
        except IntegrityError:
            LOG.exception(ex)
            return O.error(msg="Cannot delete user, some objects depend on it")
        except Exception, ex:
            LOG.exception(ex)
            request.db.rollback()
            return O.error(msg="Cannot delete user")

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
    def groups(self, name=None, **kwargs):
        def modifier(roles):
            return [dict(as_user=role.as_user, servers=role.servers)
                    for role in roles]
        if name:
            group = Group.visible(request).filter(Group.name == name).first()
            return O.group(group.serialize(
                skip=['id', 'org_id'],
                rel=[('roles', 'roles', modifier)]))
        else:
            groups = [u.serialize(
                skip=['id', 'org_id'],
                rel=[('roles', 'roles', modifier)])
                for u in Group.visible(request).all()]
            return O.groups(_list=groups)

    @groups.when(method='POST', template='json')
    @signal('manage.groups', 'create',
            when=lambda r: not r.get("error"))
    def add_group(self, name, *args, **kwargs):
        name = name or kwargs['name']
        try:
            org = request.db.query(Org).filter(
                Org.name == request.user.org).one()
            group = Group(name=name, org=org)
            request.db.add(group)
            request.db.commit()
            return O.success(status="ok")
        except IntegrityError:
            request.db.rollback()
            return O.error(msg="Group name is already taken",
                           field="name")
        except Exception, ex:
            LOG.exception(ex)
            request.db.rollback()
            return O.error(msg="Cannot create group")

    @groups.when(method='PUT', template='json')
    @signal('manage.groups', 'update',
            when=lambda r: not r.get("error"))
    def modify_group_roles(self, name, *args, **kwargs):
        name = name or kwargs['name']
        add_roles = request.POST.getall('add')
        rm_roles = request.POST.getall('remove')
        try:
            group = Group.visible(request).filter(Group.name == name).first()
            if not group:
                return O.error(msg="Group is not available")

            for role in rm_roles:
                as_user, _, servers = role.partition("@")
                if not as_user or not servers:
                    continue
                roles = [r for r in group.roles if r.as_user == as_user and
                         r.servers == servers]
                for r in roles:
                    request.db.delete(r)

            for role in add_roles:
                as_user, _, servers = role.partition("@")
                if not as_user or not servers:
                    continue
                r = Role(as_user=as_user, servers=servers, group=group)
                try:
                    request.db.add(r)
                    request.db.commit()
                except IntegrityError:
                    request.db.rollback()
            return O.success(status="ok")
        except Exception, ex:
            LOG.exception(ex)
            request.db.rollback()
            return O.error(msg="Cannot create group")

    @groups.when(method='DELETE', template='json')
    @signal('manage.groups', 'delete',
            when=lambda r: not r.get("error"))
    def rm_group(self, name, **kwargs):
        try:
            group = Group.visible(request).filter(Group.name == name).first()
            if not group:
                return O.error(msg="Group not found")

            request.db.delete(group)
            request.db.commit()
            return O.success(status='ok')
        except IntegrityError:
            LOG.exception(ex)
            return O.error(msg="Cannot delete group, "
                           "some objects may depend on it")
        except Exception, ex:
            LOG.exception(ex)
            request.db.rollback()
            return O.error(msg="Cannot delete group")

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
