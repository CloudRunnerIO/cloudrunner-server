import logging
from pecan import request, response
from mako.template import Template
from sqlalchemy import or_
from sqlalchemy.orm import exc

from cloudrunner_server.api.model import Script, User, Org
from cloudrunner_server.api.hooks.zmq_hook import ZmqHook

LOG = logging.getLogger()


class ZmqMixin(object):
    __hooks__ = [ZmqHook()]


class DbMixin(object):
    __hooks__ = []


class SseRenderer(object):

    def __init__(self, path, extra_vars):
        pass

    def render(self, template_path, res):
        _res = []
        if res.id:
            _res.append("id: %s" % res.id)
        if res.event:
            _res.append("event: %s" % res.event)
        _data = res.data
        if _data:
            _res.extend(res.data)

        return response  # "\n".join(_res)


class LibraryRenderer(object):

    def __init__(self, path, extra_vars):
        self.path = path

    def render(self, template_path, res):
        try:
            inl = request.db.query(Script).join(User, Org).filter(
                Org.name == request.user.org,
                Script.name == template_path,
                or_(Script.private == None,  # noqa
                    Script.private == False,  # noqa
                    User.id == request.user.id)).one()
        except exc.NoResultFound, ex:
            LOG.error(ex)
            request.db.rollback()
            return ("Template %s not found in the inline library" %
                    template_path)

        template = Template(inl.content)

        return template.render(**res)
