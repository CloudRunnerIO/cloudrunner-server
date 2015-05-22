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

from cloudrunner import VAR_DIR
import json
import logging
import os
import requests

from .base import BaseCloudProvider, CR_SERVER

LOG = logging.getLogger()
HEADERS = {'Content-Type': 'application/json'}


class DockerHost(BaseCloudProvider):

    def __init__(self, profile):
        super(DockerHost, self).__init__(profile)

        prefix = "%s-%s" % (self.profile.owner.org, self.profile.id)
        self._path = os.path.join(VAR_DIR, "tmp", "creds", prefix)
        self._cert_path = os.path.join(
            VAR_DIR, "tmp", "creds", prefix, 'cert.pem')
        self._key_path = os.path.join(
            VAR_DIR, "tmp", "creds", prefix, 'key.pem')
        if (not os.path.exists(self._cert_path) or
                not os.path.exists(self._key_path)):
            if not os.path.exists(self._path):
                os.makedirs(self._path, mode=500)
            # Re-create files if missing
            with open(self._cert_path, 'w') as f:
                f.write(self.profile.username)
            with open(self._key_path, 'w') as f:
                f.write(self.profile.password)

    def create_machine(self, name, server_address,
                       image, server=CR_SERVER,
                       port_bindings=None, privileged=False,
                       volume_bindings=None, **kwargs):
        ports = {}
        volumes = {}
        if port_bindings:
            for binding in port_bindings:
                ports[binding] = {}
        if volume_bindings:
            for binding in volume_bindings:
                volumes[binding] = {}
        # cmd = PROVISION % dict(server=server,
        #                        name=name,
        #                        api_key=self.api_key)
        env = ["SERVER_ID=master.cloudrunner.io",
               "ORG_ID=%s" % self.api_key]
        json_data = dict(Hostname=name, Image=image, Env=env,
                         ExposedPorts=ports, Privileged=privileged,
                         Volumes=volumes,
                         Tty=True,
                         OpenStdin=True,)
        # Cmd=[cmd],
        # Entrypoint=['/bin/curl'])
        create_url = "https://%s/containers/create" % server_address

        try:
            server_ids = []
            res = requests.post(create_url, data=json.dumps(json_data),
                                cert=(self._cert_path,
                                      self._key_path),
                                headers=HEADERS,
                                verify=False)
            if res.status_code >= 300:
                LOG.error("FAILURE %s(%s)" % (res.status_code, res.content))
                return self.FAIL, [], {}
            server_id = res.json()['Id']
            server_ids.append(server_id)
            start_url = "https://%s/containers/%s/start" % (server_address,
                                                            server_id)
            res = requests.post(start_url, data=json.dumps({"Detach": False,
                                                            "Tty": False}),
                                cert=(self._cert_path,
                                      self._key_path),
                                headers=HEADERS,
                                verify=False)
            meta = dict(server_address=server_address)
        except Exception, ex:
            LOG.exception(ex)
            raise

        return self.OK, server_ids, meta

    def delete_machine(self, server_ids, server_address=None, **kwargs):
        ret = self.OK
        for server_id in server_ids:
            delete_url = "https://%s/containers/%s" % (server_address,
                                                       server_id)
            res = requests.delete(delete_url, cert=(self._cert_path,
                                                    self._key_path),
                                  headers=HEADERS,
                                  verify=False)
            if res.status_code >= 300:
                LOG.error("FAILURE %s(%s)" % (res.status_code, res.content))
                ret = self.FAIL
        return ret
