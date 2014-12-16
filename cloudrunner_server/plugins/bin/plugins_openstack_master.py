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


def install():
    print "Installing CloudRunner OpenStack Plugin"
    from cloudrunner import CONFIG_LOCATION
    from cloudrunner.util.config import Config

    print "Found master config in %s" % CONFIG_LOCATION

    config = Config(CONFIG_LOCATION)

    config.update('Plugins', 'openstack',
                  'cloudrunner_server.plugins.auth.openstack_verifier')
    config.reload()

    print "Cloudrunner OpenStack configuration completed"

if __name__ == '__main__':
    install()
