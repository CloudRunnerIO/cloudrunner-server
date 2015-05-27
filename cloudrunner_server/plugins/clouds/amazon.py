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

from boto import ec2
import logging

from .base import BaseCloudProvider, PROVISION, CR_SERVER

LOG = logging.getLogger()


class AWS(BaseCloudProvider):

    def create_machine(self, name, region='us-west-2',
                       image=None, inst_type=None,
                       min_count=1, max_count=1,
                       server=CR_SERVER,
                       security_groups=None,
                       key_name=None, **kwargs):
        LOG.info("Registering AWS machine [%s::%s] for [%s]" %
                 (name, image, CR_SERVER))
        try:
            self.conn = ec2.connect_to_region(
                region,
                aws_access_key_id=self.profile.username,
                aws_secret_access_key=self.profile.password)

            boot_cmd = PROVISION % dict(server=server, name=name,
                                        api_key=self.api_key)
            res = self.conn.run_instances(
                image,
                min_count=min_count, max_count=max_count,
                user_data="#!/bin/bash\n\n%s" % boot_cmd,
                instance_type=inst_type,
                key_name=key_name,
                security_groups=security_groups)

            instance_ids = [inst.id for inst in res.instances]
            self.conn.create_tags(instance_ids, {"Name": name})
            meta = dict(region=region)
            return self.OK, instance_ids, meta
        except Exception, ex:
            LOG.exception(ex)
            return self.FAIL, [], {}

    def delete_machine(self, instance_ids, region='us-west-2', **kwargs):
        self.conn = ec2.connect_to_region(
            region,
            aws_access_key_id=self.profile.username,
            aws_secret_access_key=self.profile.password)
        try:
            self.conn.terminate_instances(instance_ids)
        except Exception, ex:
            LOG.exception(ex)
            return self.FAIL
        return self.OK
