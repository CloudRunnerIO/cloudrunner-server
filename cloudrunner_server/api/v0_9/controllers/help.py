#!/usr/bin/python
# -*- coding: utf-8 -*-
# vim: tabstop=4 shiftwidth=4 softtabstop=4

# /*******************************************************
#  * Copyright (C) 2013-2014 CloudRunner.io <info@cloudrunner.io>
#  *
#  * Proprietary and confidential
#  * This file is part of CloudRunner Server.
#  *
#  * CloudRunner Server can not be copied and/or distributed
#  * without the express permission of CloudRunner.io
#  *******************************************************/

from pecan import expose


class HtmlDocs():

    @expose(generic=True, template='html/index.html')
    def index(self):
        return {}

    @expose(template='html/auth.html')
    def auth(self):
        return {}

    @expose(template='html/dispatch.html')
    def dispatch(self):
        return {}

    @expose(template='html/library.html')
    def library(self):
        return {}

    @expose(template='html/logs.html')
    def logs(self):
        return {}

    @expose(template='html/manage.html')
    def manage(self):
        return {}

    @expose(template='html/scheduler.html')
    def scheduler(self):
        return {}

    @expose(template='html/triggers.html')
    def triggers(self):
        return {}
