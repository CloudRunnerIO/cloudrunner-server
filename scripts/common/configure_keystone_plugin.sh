#!/bin/bash
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


set -e

if [ ! ~/keystonerc_admin ] ;then
    echo no openstack credentials
    exit 1
fi

admin_tenant=$(keystone tenant-list | grep admin | cut -f 2 -d '|')
admin_role=$(keystone role-list | grep admin | cut -f 2 -d '|')

keystone user-create --name cloudrunner_admin --pass sd@d_Lieir985 --tenant_id $admin_tenant --email admin@cloudrunner.io

user_id=$(keystone user-list | grep cloudrunner_admin | cut -f 2 -d '|')

keystone user-role-add --tenant_id $admin_tenant --user $user_id --role $admin_role
