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

from pecan import abort, request  # noqa
from pecan.hooks import PecanHook


class PermHook(PecanHook):

    priority = 1

    def __init__(self, have=None, dont_have=None):
        super(PermHook, self).__init__()
        self.should_have = set()
        self.should_not_have = set()

        def check_have(perms):
            return self.should_have.intersection(perms)

        def check_dont_have(perms):
            return not self.should_not_have.intersection(perms)

        self.checks = []

        if have:
            self.should_have = have
            self.checks.append(check_have)
        if dont_have:
            self.should_not_have = dont_have
            self.checks.append(check_dont_have)

    def before(self, state):
        p = request.user.permissions

        for check in self.checks:
            if not check(p):
                abort(401)
