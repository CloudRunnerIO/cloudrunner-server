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

from azure.servicemanagement import (ServiceManagementService,
                                     LinuxConfigurationSet,
                                     OSVirtualHardDisk)
import os
import tempfile

from cloudrunner import VAR_DIR
from .base import BaseCloudProvider, CR_SERVER  # , PROVISION

URL = "https://management.core.windows.net/%(username)s/services/hostedservices/%(service)s/deployments"  # noqa


class Azure(BaseCloudProvider):

    def __init__(self, profile, log=None):
        super(Azure, self).__init__(profile, log)
        prefix = "%s-%s" % (self.profile.owner.org, self.profile.id)
        self._path = os.path.join(VAR_DIR, "tmp", "creds", prefix)
        self.server_address = self.profile.username
        _, self._cert_path = tempfile.mkstemp(dir=self._path,
                                              suffix='pem',
                                              text=True)

    def _cleanup(self):
        os.unlink(self._cert_path)

    def create_machine(self, name, region='West US',
                       image=None, role_size='Small',
                       min_count=1, max_count=1,
                       media='storage_url_blob_cloudrunner',
                       username='', password='', ssh_pub_key='',
                       server=CR_SERVER,
                       cleanup=None, **kwargs):
        self.log.info("Registering Azure machine [%s::%s] for [%s]" %
                      (name, image, CR_SERVER))
        try:
            sms = ServiceManagementService(self.profile.username,
                                           self._cert_path)
            server_config = LinuxConfigurationSet('myhostname', 'myuser',
                                                  'mypassword', True)
            media_link = "%s__%s" % (media, name)
            os_hd = OSVirtualHardDisk(image, media_link)

            res = sms.create_virtual_machine_deployment(
                service_name=name,
                deployment_name=name,
                deployment_slot='production',
                label=name,
                role_name=name,
                system_config=server_config,
                os_virtual_hard_disk=os_hd,
                role_size='Small')

            instance_ids = []
            meta = {}
            if not res:
                return self.FAIL, [], {}
            meta['deployment_name'] = name
            meta['cleanup_service'] = cleanup in ['1', 'True', 'true']
            return self.OK, instance_ids, meta
        except Exception, ex:
            self.log.exception(ex)
            return self.FAIL, [], {}

    def delete_machine(self, instance_ids, deployment_name=None,
                       cleanup_service=None, **kwargs):
        sms = ServiceManagementService(self.profile.username,
                                       self.cert_path)
        for inst in instance_ids:
            try:
                sms.delete_deployment(service_name=inst,
                                      deployment_name=deployment_name)
                if cleanup_service:
                    sms.delete_hosted_service(service_name=inst)

            except Exception, ex:
                self.log.exception(ex)
                return self.FAIL
        return self.OK
