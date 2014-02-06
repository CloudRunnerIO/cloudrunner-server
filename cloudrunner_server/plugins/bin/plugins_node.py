#!/usr/bin/python
# -*- coding: utf-8 -*-
# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2013 CloudRunner.IO
# All Rights Reserved.

from os import path as p


def install():
    print "Installing CloudRunner Node Plugin"
    from cloudrunner import CONFIG_NODE_LOCATION
    from cloudrunner.util.config import Config

    print "Found config in %s" % CONFIG_NODE_LOCATION

    config = Config(CONFIG_NODE_LOCATION)
    _path = p.abspath(p.join(p.dirname(__file__), '..', 'transport'))

    config.update('General', 'transport',
                  'cloudrunner_plugins.transport.zmq_node_transport.NodeTransport')
    config.update('Plugins', 'node_config',
                  'cloudrunner_plugins.config.ssl_config')
    config.reload()

    print "Node configuration completed"

if __name__ == '__main__':
    install()
