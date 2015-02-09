from pecan import expose, request
from pecan.hooks import HookController

from cloudrunner_server.api.decorators import wrap_command
from cloudrunner_server.api.hooks.db_hook import DbHook
from cloudrunner_server.api.hooks.error_hook import ErrorHook
from cloudrunner_server.api.model import User
from cloudrunner_server.api.util import JsonOutput as O


class Profile(HookController):

    __hooks__ = [DbHook(), ErrorHook()]

    @expose('json', generic=True)
    @wrap_command(User)
    def profile(self, *args, **kwargs):
        user = User.visible(request).filter(
            User.username == request.user.username).one()
        return O.user(quotas=request.user.tier._items,
                      plan=request.user.tier.name,
                      **user.serialize(
                          skip=['id', 'org_id', 'password'],
                          rel=[('groups.name', 'groups')]))

    @profile.when(method='PATCH', template='json')
    @profile.wrap_modify()
    def profile_update(self, **kwargs):
        user = User.visible(request).filter(
            User.username == request.user.username).one()
        for k in set(kwargs.keys()).intersection(User.attrs):
            setattr(user, k, kwargs[k])
        request.db.add(user)

    @profile.when(method='PUT', template='json')
    @profile.wrap_modify()
    def profile_replace(self, **kwargs):
        for k in User.attrs:
            kwargs[k]
        return self.profile_update(**kwargs)
