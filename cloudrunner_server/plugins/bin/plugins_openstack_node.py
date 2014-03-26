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
    from cloudrunner import CONFIG_NODE_LOCATION
    from cloudrunner.util.config import Config

    print "Found node config in %s" % CONFIG_NODE_LOCATION

    config = Config(CONFIG_NODE_LOCATION)
    _path = p.abspath(p.join(p.dirname(__file__), '..', 'transport'))

    config.update('General', 'transport',
                  'cloudrunner_plugins.transport.zmq_node_transport.NodeTransport')
    config.update('Plugins', 'config',
                  'cloudrunner_plugins.config.openstack_ssl_config')
    config.reload()

    print "Cloudrunner node configuration completed"

if __name__ == '__main__':
    install()
