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


class DigitalOcean(BaseCloudProvider):

    def create_machine(self, name, image=None, server=CR_SERVER,
                       inst_type='512MB', region='nyc3',
                       port_bindings=None, privileged=False,
                       ssh_keys=None,
                       volume_bindings=None, **kwargs):
        ports = {}
        volumes = {}
        if port_bindings:
            for binding in port_bindings:
                ports[binding] = {}
        if volume_bindings:
            for binding in volume_bindings:
                volumes[binding] = {}
        LOG.info("Registering DigitalOcean machine [%s::%s] for [%s]" %
                 (name, image, CR_SERVER))

        cmd = PROVISION % dict(server=server, name=name, api_key=self.api_key)
        json_data = dict(name=name, region=region, size=inst_type,
                         image=image, ssh_keys=ssh_keys,
                         user_data="#!/bin/bash\n\n%s" % cmd,
                         backups=False,
                         ipv6=True,
                         private_networking=None)
        headers = {'Content-Type': 'application/json',
                   'Authorization': 'Bearer %s' % self.profile.password}

        url = 'https://api.digitalocean.com/v2/droplets'
        try:
            instance_ids = []
            res = requests.post(url, data=json.dumps(json_data),
                                headers=headers)
            if res.status_code >= 300:
                LOG.error("FAILURE %s(%s) [[%s]]" % (res.status_code,
                                                     res.content,
                                                     json_data
                                                     ))
                return self.FAIL, [], {}

            json_res = res.json()
            instance_ids.append(json_res['droplet']['id'])

            meta = dict(region=region)
            return self.OK, instance_ids, meta
        except Exception, ex:
            LOG.exception(ex)
            LOG.warn(json_data)
            raise

        return self.FAIL, [], {}

    def delete_machine(self, instance_ids, **kwargs):
        headers = {'Content-Type': 'application/json',
                   'Authorization': 'Bearer %s' % self.profile.password}

        for iid in instance_ids:
            url = 'https://api.digitalocean.com/v2/droplets/%s' % iid
            try:
                res = requests.delete(url, headers=headers)
                if res.status_code >= 300:
                    LOG.error("FAILURE %s(%s)" %
                              (res.status_code, res.content))
                    return self.FAIL

                return self.OK
            except Exception, ex:
                LOG.exception(ex)
                raise
