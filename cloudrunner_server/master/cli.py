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

import sys
try:
    import argcomplete
except ImportError:
    pass
import argparse

from cloudrunner import CONFIG_LOCATION
from cloudrunner.util.config import Config
from cloudrunner.util.shell import colors
from cloudrunner_server.master import functions

__CONFIG__ = None
__ACT_NODES__ = None
__PEND_NODES__ = None
__CA__ = None
__USERS__ = None
__ORG__ = None


def main():
    parser = argparse.ArgumentParser(description='CloudRunner CLI tool')

    _common = argparse.ArgumentParser(add_help=False)
    _common.add_argument('-c', '--config', help="Config file")

    commands = parser.add_subparsers(dest='controller', help='Commands')

    def _eval_config():
        global __CONFIG__
        if not __CONFIG__:
            try:
                if sys.argv.index('-c') >= 0:
                    __CONFIG__ = Config(sys.argv[sys.argv.index('-c') + 1])
                elif sys.argv.index('--config') >= 0:
                    __CONFIG__ = Config(sys.argv[sys.argv.index('--config') +
                                                 1])
            except:
                __CONFIG__ = Config(CONFIG_LOCATION)

        return __CONFIG__

    def _list_active_nodes(prefix, parsed_args, **kwargs):
        global __ACT_NODES__
        if not __ACT_NODES__:
            _config = _eval_config()
            __ACT_NODES__ = functions.CertController(_config).\
                list_all_approved()
        return (c for c in __ACT_NODES__ if c.startswith(prefix))

    def _list_pending_nodes(prefix, parsed_args, **kwargs):
        global __PEND_NODES__
        if not __PEND_NODES__:
            _config = _eval_config()
            __PEND_NODES__ = functions.CertController(_config).list_pending()
        return (c for c in __PEND_NODES__ if c.startswith(prefix))

    def _list_sub_ca(prefix, parsed_args, **kwargs):
        global __CA__
        if not __CA__:
            _config = _eval_config()
            __CA__ = functions.CertController(_config).list_ca()
        return (c[1] for c in __CA__ if c[1].startswith(prefix))

    # Cert command
    cert = commands.add_parser('cert', parents=[_common],
                               help='Manage node certificates')

    c_subcmd = cert.add_subparsers(dest='action', help='Cert actions help')

    c_subcmd.add_parser('list',
                        help='List all node certificates')

    cert_sign = c_subcmd.add_parser('sign',
                                    help='Sign a pending node certificate')
    cert_sign.add_argument('node', nargs="+",
                           help='Node common name').completer = \
        _list_pending_nodes

    if _eval_config().security.use_org:
        sign_opts = cert_sign.add_mutually_exclusive_group(required=True)
        sign_opts.add_argument('--ca', help='Node organization/Sub-CA name').\
            completer = _list_sub_ca
        sign_opts.add_argument('--auto', action='store_true',
                               help='Get organization from client request')

    cert_ca = c_subcmd.add_parser('create_ca',
                                  help='Create an organization CA certificate')
    cert_ca.add_argument('ca',
                         help='Org/Sub-CA name')

    c_subcmd.add_parser('list_ca', help='List organizations/'
                        'Sub-CA certificates')

    cert_auto_sign = c_subcmd.add_parser('autosign',
                                         help='Automatically sign a node '
                                         'certificate with the specified name,'
                                         ' when it arrives')
    cert_auto_sign.add_argument('node',
                                help='Node common name')

    cert_auto_sign.add_argument(
        '--expires', default=20,
        help='Set expiration of the auto-sign notice in minutes. '
        'Default is %d(default) min')

    cert_revoke = c_subcmd.add_parser('revoke',
                                      help='Revoke already issued certificate')
    cert_revoke.add_argument('node', nargs="+", help='Node common name').\
        completer = _list_active_nodes

    if _eval_config().security.use_org:
        cert_revoke.add_argument('--ca', required=True,
                                 help='Node organization/Sub-CA name').\
            completer = _list_sub_ca

    cert_revoke_ca = c_subcmd.add_parser('revoke_ca',
                                         help='Revoke existing Sub-CA')
    cert_revoke_ca.add_argument('ca',
                                help='Sub-CA name').completer = _list_sub_ca

    cert_auto = c_subcmd.add_parser('autosign',
                                    help='Automatically sign new cert request '
                                         'in a limited time frame.')
    cert_auto.add_argument('node',
                           help='Node common name')

    cert_auto.add_argument('-t', '--timeout', default=120,
                           help='Allowed time frame in seconds'
                           ' to wait for node to make request.'
                           ' Default is %(default)s sec.',
                           required=False)

    clear_req = c_subcmd.add_parser('clear_req',
                                    help='Clear pending node request')
    clear_req.add_argument('node', nargs="+", help='Node common name').\
        completer = _list_pending_nodes

    if _eval_config().security.use_org:
        clear_req.add_argument('--ca', help='Node organization/Sub-CA name',
                               required=True).completer = _list_sub_ca

    # Configure command

    config = commands.add_parser('config', parents=[_common],
                                 help='Initial certificate configuration')

    config_actions = config.add_subparsers(dest='action',
                                           help='Manage CloudRunner dispatcher'
                                           ' configuration')

    config_actions.add_parser('check',
                              help='Check if config is missing '
                              'and initiate fresh configuration')

    config_new = config_actions.add_parser('create',
                                           help='Create new configuration')

    config_new.add_argument('-p', '--path',
                            help='Create initial configuration'
                            ' at the specified location. '
                            'This will make all currently '
                            'registered nodes to stop working'
                            'and all signed certificates will '
                            'be no longer valid',
                            required=False)

    config_new.add_argument('-o', '--overwrite',
                            action='store_true',
                            help='Overwrite any existing '
                            'configuration. Use with caution!',
                            required=False)

    config_new.add_argument('-k', '--key-size', default=2048,
                            help='Default size of keys for '
                            'CA/Server. Default is %(default)s',
                            required=False)

    config_actions.add_parser('show',
                              help='Printing current configuration')

    conf_set = config_actions.add_parser('set',
                                         help='Set config values')

    conf_set.add_argument('Section.key=value',
                          help='Section.key=value')

    conf_get = config_actions.add_parser('get',
                                         help='Get config values')

    conf_get.add_argument('Section.key',
                          help='Section.key')

    # Scheduler

    scheduler = commands.add_parser('schedule', parents=[_common],
                                    help='Run scheduled jobs')

    sched_actions = scheduler.add_subparsers(dest='action',
                                             help='Manage CloudRunner '
                                             'dispatcher scheduled jobs')

    job_list = sched_actions.add_parser('list',
                                        help='List all scheduled jobs')
    job_list.add_argument('-s', '--search',
                          help='Search pattern')

    job_exec = sched_actions.add_parser('run', help='Run scheduled jobs')

    job_exec.add_argument('job_id', help='Job id')

    # Users command

    def _list_users(prefix, parsed_args, **kwargs):
        global __USERS__
        if not __USERS__:
            __USERS__ = []
            _config = _eval_config()
            for u in functions.UserController(_config, to_print=False).list():
                if u[0] == functions.DATA:
                    __USERS__.extend(u[1])
        return (c for c in __USERS__ if c.startswith(prefix))

    if _eval_config().security.use_org:
        def _list_org(prefix, parsed_args, **kwargs):
            global __ORG__
            if not __ORG__:
                __ORG__ = []
                _config = _eval_config()
                for u in functions.UserController(_config,
                                                  to_print=False).list_orgs():
                    if u[0] == functions.DATA:
                        __ORG__.extend(u[1])
            return (c[0] for c in __ORG__ if c[0].startswith(prefix))

        orgs = commands.add_parser('org', parents=[_common],
                                   help='Organization management')
        orgs_actions = orgs.add_subparsers(dest='action',
                                           help='Manage Organizations')

        orgs_actions.add_parser('list',
                                help='List all organizations')

        org_add = orgs_actions.add_parser('create',
                                          help='Create new organization')
        org_add.add_argument('name', help='Organization name')

        org_remove = orgs_actions.add_parser('remove',
                                             help='Remove organization/Sub-CA')

        org_remove.add_argument('name', help='Organization/Sub-CA name').\
            completer = _list_org

        org_activate = orgs_actions.add_parser('activate',
                                               help='Activate organization')
        org_activate.add_argument('name', help='Organization name').\
            completer = _list_org

        org_deactivate = orgs_actions.add_parser(
            'deactivate', help='Deactivate organization')

        org_deactivate.add_argument('name', help='Organization name').\
            completer = _list_org

    users = commands.add_parser('users', parents=[_common],
                                help='User management')

    users_actions = users.add_subparsers(dest='action',
                                         help='Manage CloudRunner users')

    users_actions.add_parser('list', help='List all users')

    users_actions.add_parser('list_orgs', help='List all organizations')

    users_add = users_actions.add_parser('create',
                                         help='Create new user')

    users_add.add_argument('username', help='User name')
    users_add.add_argument('password', help='Auth password')
    if _eval_config().security.use_org:
        users_add.add_argument('--org', required=True, help='Organization')

    users_role = users_actions.add_parser('add_role',
                                          help='Create new auth role')

    users_role.add_argument('username',
                            help='User name').completer = _list_users

    users_role.add_argument('node', help="Node to apply role. "
                            "Can be plain value or regex")

    users_role.add_argument('role', help="User rule to be applied. "
                            "A regex for selecting nodes")

    users_roles = users_actions.add_parser('roles',
                                           help='List roles for user')

    users_roles.add_argument('username',
                             help='User name').completer = _list_users

    users_role_rm = users_actions.add_parser('rm_role',
                                             help='Remove role for user')

    users_role_rm.add_argument('username',
                               help='User name').completer = _list_users

    users_role_rm.add_argument('node', help="Node to remove role for.")

    users_remove = users_actions.add_parser('remove',
                                            help='Create new user')

    users_remove.add_argument('username', help='User name')

    try:
        argcomplete.autocomplete(parser)
    except:
        pass

    args = parser.parse_args()

    action = args.action

    class OrgController(object):

        def __init__(self, config):
            self.cont = functions.UserController(config)

        def create(self, name, **kwargs):
            return self.cont.create_org(name)

        def activate(self, name, **kwargs):
            return self.cont.activate_org(name)

        def deactivate(self, name, **kwargs):
            return self.cont.deactivate_org(name)

        def list(self, **kwargs):
            return self.cont.list_orgs()

        def remove(self, name, **kwargs):
            return self.cont.remove_org(name)

    controllers = {'cert': functions.CertController,
                   'init': functions.ConfigController,
                   'config': functions.ConfigController,
                   'schedule': functions.SchedulerController,
                   'users': functions.UserController,
                   'org': OrgController,
                   'trigger': functions.TriggerController}
    config = Config(args.config or CONFIG_LOCATION)

    printers = {
        functions.TAG: lambda *args: colors.yellow(*args, bold=1),
        functions.DATA: colors.blue,
        functions.ERR: lambda *args: colors.red(*args, bold=1),
        functions.NOTE: colors.grey,
        functions.EMPTY: colors.blue,
    }
    try:
        items = getattr(controllers[args.controller](config),
                        action)(**vars(args))
        if not items:
            return
        for line in items:
            _type = line[0]
            printables = list(line[1:])
            for i in range(len(printables)):
                if isinstance(printables[i], list):
                    printables[i] = '\n'.join(concat(p) for p in printables[i])
            printables = [str(p) for p in printables]
            print printers[_type]('\n'.join(printables))
    except Exception, ex:
        print colors.red(str(ex))


def concat(val):
    if isinstance(val, basestring):
        return val
    else:
        return ' '.join(['%-20s' % v for v in val])

if __name__ == '__main__':
    main()
