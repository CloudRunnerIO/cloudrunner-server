#!/usr/bin/python
# -*- coding: utf-8 -*-
# vim: tabstop=4 shiftwidth=4 softtabstop=4

# /*******************************************************
#  * Copyright (C) 2013-2014 CloudRunner.io <info@cloudrunner.io>
#  *
#  * Proprietary and confidential
#  * This file is part of CloudRunner Server.
#  *
#  * CloudRunner Server can not be copied and/or distributed without the express
#  * permission of CloudRunner.io
#  *******************************************************/

from os import path as p


def install():
    print "Installing CloudRunner OpenStack Plugin"
    from cloudrunner import CONFIG_LOCATION
    from cloudrunner.util.config import Config

    print "Found master config in %s" % CONFIG_LOCATION

    config = Config(CONFIG_LOCATION)
    _path = p.abspath(p.join(p.dirname(__file__), '..', 'transport'))

    config.update('Plugins', 'openstack',
                  'cloudrunner_server.plugins.auth.openstack_verifier')
    config.reload()
    if not config.security.use_org:
        print "WARNING: Security::use_org is not set!"

    print "Cloudrunner OpenStack configuration completed"

if __name__ == '__main__':
    install()
