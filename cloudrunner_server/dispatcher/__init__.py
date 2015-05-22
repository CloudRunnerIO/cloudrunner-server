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
        self._callback = None
        self._prepare = None
        self.owner = None

    def push(self, task):
        self.tasks.append(task)

    def callback(self, task):
        self._callback = task

    def prepare(self, prepare):
        self._prepare = prepare

    def find(self, task_id):
        return filter(lambda x: x.session_id == task_id, self.tasks)

    @property
    def task_ids(self):
        return [task.session_id for task in self.tasks]

    def process(self):
        if not self.tasks:
            return
        if self._prepare:
            self._prepare.start()
        for task in self.tasks:
            task.start()
        if self._callback:
            self._callback.start()

    def __str__(self):
        return "%s (%s)" % (self.task_ids, self.owner)

    def __repr__(self):
        return "%s (%s)" % (self.task_ids, self.owner)
