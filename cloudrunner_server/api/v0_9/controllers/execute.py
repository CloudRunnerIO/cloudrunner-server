import logging
from pecan import expose, request, abort
from pecan.hooks import HookController

from cloudrunner_server.api.hooks.db_hook import DbHook
from cloudrunner_server.api.util import JsonOutput as O
from cloudrunner_server.api.model import Script, Repository, Folder, ApiKey
from cloudrunner_server.triggers.manager import TriggerManager

LOG = logging.getLogger()

MAN = TriggerManager()


class Execute(HookController):

    __hooks__ = [DbHook()]

    @expose('json')
    def script(self, *args, **kwargs):
        full_path = "/" + "/".join(args)
        LOG.info("Received execute request [%s] from: %s" % (
            full_path, request.client_addr))

        key = kwargs.pop('key')
        if not key:
            return O.error(msg="Missing auth key")

        api_key = request.db.query(ApiKey).filter(ApiKey.value == key).first()
        if not api_key:
            return abort(401)

        version = kwargs.pop("rev", None)
        repo, _dir, scr_name, rev = Script.parse(full_path)

        repo = request.db.query(Repository).filter(
            Repository.name == repo).first()
        if not repo:
            return O.error(msg="Repository '%s' not found" % repo)

        scr = request.db.query(Script).join(Folder).filter(
            Script.name == scr_name, Folder.repository_id == repo.id,
            Folder.full_name == _dir).first()
        if not scr:
            return O.error(msg="Script '%s' not found" % full_path)
        rev = scr.contents(request, rev=version)
        if not rev:
            if version:
                return O.error(msg="Version %s of script '%s' not found" %
                               (version, full_path))
            else:
                return O.error(msg="Script contents for '%s' not found" %
                               full_path)

        task_ids = MAN.execute(user_id=api_key.user_id,
                               content=rev, **kwargs)
        return O.success(msg="Dispatched", **task_ids)
