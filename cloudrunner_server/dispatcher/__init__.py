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

ADMIN_TOWER = 'cloudrunner-control'


def is_valid_host(host):
    if not host:
        return False
    return not filter(lambda x:
                      x.lower() == host.lower(), (ADMIN_TOWER.lower(),))

SCHEDULER_URI_TEMPLATE = "ipc://%(sock_dir)s/scheduler.sock"


class TaskQueue(object):

    def __init__(self):
        self.tasks = []
        self.owner = None

    @property
    def task_ids(self):
        return [task.session_id for task in self.tasks]

    def process(self):
        if not self.tasks:
            return
        for task in self.tasks:
            task.start()

    def __str__(self):
        return "[%s] (%s) /%s /%s" % (self.session_id, self.main,
                                      self.peer, self.owner)

    def __repr__(self):
        return "[%s] (%s) /%s /%s" % (self.session_id, self.main,
                                      self.peer, self.owner)
