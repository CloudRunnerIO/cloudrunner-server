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

from .base import BaseCloudProvider, PROVISION, CR_SERVER

LOG = logging.getLogger()
AUTH_URL = "https://identity.api.rackspacecloud.com/v2.0/tokens"


class Rax(BaseCloudProvider):

    def create_machine(self, name, image=None, region='ord',
                       flavor='2',
                       key_name=None,
                       metadata=None,
                       networks=None,
                       **kwargs):
        LOG.info("Registering AWS machine [%s::%s] for [%s]" %
                 (name, image, CR_SERVER))
        cmd = PROVISION % dict(server=CR_SERVER,
                               name=name,
                               api_key=self.api_key)
        json_data = dict(name=name, flavorRef=flavor,
                         imageRef=image, key_name=key_name,
                         user_data="#!/bin/bash\n\n%s" % cmd,
                         config_drive=True,
                         metadata=metadata,
                         networks=networks)

        headers = {'Content-Type': 'application/json'}

        try:
            server_ids, meta = [], dict(region=region)
            res = requests.post(AUTH_URL, data=self._auth_data,
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
                return self.FAIL, [], {}
            server_ids.append(res.json()['server']['id'])
        except Exception, ex:
            LOG.exception(ex)
            return self.FAIL, [], {}

        return self.OK, server_ids, meta

    def delete_machine(self, server_ids, region='ord', **kwargs):
        ret = self.OK
        try:
            for server_id in server_ids:
                headers = {'Content-Type': 'application/json'}
                res = requests.post(AUTH_URL, data=self._auth_data,
                                    headers=headers)
                if res.status_code >= 300:
                    LOG.error("FAILURE %s(%s)" %
                              (res.status_code, res.content))
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

                endpoint_url = '%s/servers/%s' % (endpoints[0], server_id)
                headers['X-Auth-Token'] = auth_token
                res = requests.delete(endpoint_url, headers=headers)
                if res.status_code >= 300:
                    LOG.error("FAILURE %s(%s)" %
                              (res.status_code, res.content))
                    ret = self.FAIL
        except Exception, ex:
            LOG.exception(ex)
            ret = self.FAIL

        return ret

    @property
    def _auth_data(self):
        return json.dumps({
            "auth":
            {
                "RAX-KSKEY:apiKeyCredentials":
                {
                    "username": self.profile.username,
                    "apiKey": self.profile.password
                }
            }
        })
