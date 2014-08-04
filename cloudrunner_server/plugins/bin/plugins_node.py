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
    print "Installing CloudRunner Node Plugin"
    from cloudrunner import CONFIG_NODE_LOCATION
    from cloudrunner.util.config import Config

    print "Found config in %s" % CONFIG_NODE_LOCATION

    config = Config(CONFIG_NODE_LOCATION)

    config.update('General', 'transport',
                  'cloudrunner_plugins.transport.'
                  'zmq_node_transport.NodeTransport')
    config.reload()

    print "Node configuration completed"

if __name__ == '__main__':
    install()
