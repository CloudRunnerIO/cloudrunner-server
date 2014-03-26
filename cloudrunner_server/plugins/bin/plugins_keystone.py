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
import sys

try:
    from keystoneclient.v2_0 import client
    from keystoneclient.apiclient.exceptions import Unauthorized
except ImportError:
    print "Keystone client is not installed, it is required by the plugin. " \
        "Configuration is aborted"


def install():
    print "Installing CloudRunner Keystone Plugin"
    from cloudrunner import CONFIG_LOCATION
    from cloudrunner.util.config import Config

    print "Found master config in %s" % CONFIG_LOCATION

    config = Config(CONFIG_LOCATION)
    _path = p.abspath(p.join(p.dirname(__file__), '..', 'transport'))

    DEFAULT_URL = config.auth_url or "http://127.0.0.1:5000/v2.0"
    print "Enter Keystone AUTH URL (Hit ENTER for default: %s)" % DEFAULT_URL
    auth_url = raw_input('> ')
    if not auth_url:
        auth_url = DEFAULT_URL

    DEFAULT_ADMIN_URL = auth_url.replace(':5000', ':35357')
    print "Enter Keystone AUTH ADMIN URL (Hit ENTER for default: %s)" % \
        DEFAULT_ADMIN_URL
    admin_url = raw_input('> ')
    if not admin_url:
        admin_url = DEFAULT_ADMIN_URL

    if config.auth_user:
        print "Enter Keystone admin user (Hit ENTER for default: %s)" % \
            config.auth_user
        admin_user = raw_input('> ')
        if not admin_user:
            admin_user = config.auth_user
    else:
        print "Enter Keystone admin user:"
        admin_user = raw_input('> ')

    if config.auth_pass:
        print "Enter Keystone admin password (Hit ENTER for default: %s)" % \
            config.auth_pass
        admin_pass = raw_input('> ')
        if not admin_pass:
            admin_pass = config.auth_pass
    else:
        print "Enter Keystone admin password:"
        admin_pass = raw_input('> ')

    print "Testing connection to Keystone server:"

    class ConfigMock(object):

        def __init__(self, url, admin_url, user, password):
            self.auth_url = url
            self.auth_admin_url = admin_url
            self.auth_user = user
            self.auth_pass = password
            self.auth_admin_tenant = None
            self.auth_timeout = None
            self.token_expiration = None

    mock_config = ConfigMock(auth_url, admin_url, admin_user, admin_pass)

    from cloudrunner_server.plugins.auth.keystone_auth import KeystoneAuth
    auth = KeystoneAuth(mock_config)
    try:
        print "Loading tenants:"
        for x in auth.list_orgs():
            print x
    except Unauthorized:
        print "The plugin cannot reach the Keystone server. " \
            "Configuration aborted. Check settings"
        sys.exit(1)

    config.update('General', 'auth',
                  'cloudrunner_server.plugins.auth.keystone_auth.KeystoneAuth')
    config.update('General', 'auth_url', auth_url)
    config.update('General', 'auth_admin_url', admin_url)
    config.update('General', 'auth_user', admin_user)
    config.update('General', 'auth_pass', admin_pass)
    config.reload()

    if not config.security.use_org:
        print "WARNING: Security::use_org is not set!"

    print "Keystone configuration completed"

if __name__ == '__main__':
    install()
