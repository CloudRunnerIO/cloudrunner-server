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

import json
import logging
import requests

from .base import BaseCloudProvider, PROVISION

LOG = logging.getLogger()


class Rax(BaseCloudProvider):

    def __init__(self, config, credentials):
        self.credentials = credentials

    def create_machine(self, name, server_address, image, region='ord',
                       server='master.cloudrunner.io',
                       flavor='2',
                       key_name=None,
                       metadata=None,
                       networks=None,
                       **kwargs):
        cmd = PROVISION % dict(server=server,
                               name=name,
                               api_key=self.credentials.api_key)
        json_data = dict(name=name, flavorRef=flavor,
                         imageRef=image, key_name=key_name,
                         user_data="#!/bin/bash\n\n%s" % cmd,
                         config_drive=True,
                         metadata=metadata,
                         networks=networks)

        headers = {'Content-Type': 'application/json'}
        auth_data = {
            "auth":
            {
                "RAX-KSKEY:apiKeyCredentials":
                {
                    "username": self.credentials.user,
                    "apiKey": self.credentials.password
                }
            }
        }

        auth_url = "https://identity.api.rackspacecloud.com/v2.0/tokens"

        try:
            res = requests.post(auth_url, data=json.dumps(auth_data),
                                headers=headers)
            if res.status_code >= 300:
                LOG.error("FAILURE %s(%s)" % (res.status_code, res.content))
                return self.FAIL
            json_res = res.json()
            auth_token = json_res['access']['token']['id']
            catalogs = [c for c in json_res['access']['serviceCatalog']
                        if c['type'] == 'compute']
            endpoints = []
            for cat in catalogs:
                endpoints.extend(
                    [c['publicURL'] for c in cat['endpoints']
                     if c.get('region', '').lower() == region.lower()])

            if not endpoints:
                raise Exception("Region '%s' not found" % region)

            endpoint_url = '%s/servers' % endpoints[0]

        except Exception, ex:
            LOG.exception(ex)
            raise Exception("Rackspace: authentication problem")

        try:
            headers['X-Auth-Token'] = auth_token
            res = requests.post(endpoint_url, data=json.dumps(json_data),
                                headers=headers)
            if res.status_code >= 300:
                LOG.error("FAILURE %s(%s)" % (res.status_code, res.content))
                return self.FAIL
        except Exception, ex:
            LOG.exception(ex)
            return self.FAIL

        return self.OK

    def delete_machine(self, name, *args, **kwargs):
        pass
