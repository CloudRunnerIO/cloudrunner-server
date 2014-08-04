from pecan import expose, request
from pecan.hooks import HookController
import re

from cloudrunner.core import parser

from cloudrunner_server.api.hooks.db_hook import DbHook
from cloudrunner_server.api.hooks.error_hook import ErrorHook
from cloudrunner_server.api.hooks.signal_hook import SignalHook, signal
from cloudrunner_server.api.hooks.zmq_hook import ZmqHook
from cloudrunner_server.api.model import Log, Step, Tag, LOG_STATUS
from cloudrunner_server.api.util import JsonOutput as O


class Dispatch(HookController):

    __hooks__ = [DbHook(), ZmqHook(), ErrorHook(), SignalHook()]

    @expose('json')
    def active_nodes(self):
        success, nodes = request.zmq("list_active_nodes",
                                     return_type="json")
        if success:
            return O.nodes(_list=nodes)
        else:
            return O.error(msg=nodes)

    @expose('json')
    def nodes(self):
        success, nodes = request.zmq("list_nodes",
                                     return_type="json")
        if success:
            return O.nodes(_list=nodes)
        else:
            return O.error(msg=nodes)

    @expose('json')
    def pending_nodes(self):
        success, nodes = request.zmq("list_pending_nodes",
                                     return_type="json")
        if success:
            return O.nodes(_list=nodes)
        else:
            return O.error(msg=nodes)

    @expose('json')
    @signal('activities', 'add',
            when=lambda x: bool(x.get("dispatch")))
    def execute(self, **kwargs):
        if request.method != "POST":
            return O.dispatch(error="Use POST method instead")

        try:
            if request.headers['Content-Type'].find("x-www-form-urlencoded"):
                kw = kwargs
            else:
                kw = request.json_body
            script = kw['data']
            timeout = kw.get('timeout', 0)
            tags = re.split('[\s,;]', kw.get('tags', ''))
            log = Log(exit_code=-99,
                      status=LOG_STATUS.Running,
                      timeout=timeout,
                      owner_id=request.user.id)
            for tag in tags:
                log.tags.append(Tag(name=tag))

            sections = parser.parse_sections(script)
            for section in sections:
                timeout = section.args.get('timeout', timeout)

                step = Step(timeout=timeout, lang='bash',
                            target=section.target,
                            script=section.script,
                            env_in=kwargs.get('env'),
                            log=log)
                request.db.add(step)

            uuid = request.zmq('dispatch', **kw)
            if uuid:
                # Update
                log.uuid = uuid
            request.db.add(log)
            request.db.commit()

        except KeyError, kerr:
            return O.error(msg="Missing value: %s" % kerr)
        return O.dispatch(uuid=uuid)

    @expose('json')
    def term(self, command):
        if not command or command.lower() not in ['term', 'quit']:
            return dict(error="Unknown termination command: %s" % command)
