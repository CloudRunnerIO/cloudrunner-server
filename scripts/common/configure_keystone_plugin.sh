#!/bin/bash

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
