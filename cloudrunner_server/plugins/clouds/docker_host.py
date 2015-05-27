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
import os
import requests
import tempfile

from cloudrunner import VAR_DIR
from .base import BaseCloudProvider, CR_SERVER

LOG = logging.getLogger()
HEADERS = {'Content-Type': 'application/json'}


class Docker(BaseCloudProvider):

    def __init__(self, profile):
        super(Docker, self).__init__(profile)

        prefix = "%s-%s" % (self.profile.owner.org.name, self.profile.id)
        self._path = os.path.join(VAR_DIR, "tmp", "creds", prefix)
        if ":" in self.profile.username:
            self.server_address = self.profile.username
        else:
            self.server_address = "%s:2376" % self.profile.username
        try:
            os.makedirs(self._path)
        except:
            pass
        _, self._cert_path = tempfile.mkstemp(dir=self._path,
                                              suffix='pem',
                                              text=True)
        _, self._key_path = tempfile.mkstemp(dir=self._path,
                                             suffix='pem',
                                             text=True)

        with open(self._cert_path, 'w') as f:
            f.write(self.profile.password)
        with open(self._key_path, 'w') as f:
            f.write(self.profile.arguments)

    def _cleanup(self):
        os.unlink(self._cert_path)
        os.unlink(self._key_path)

    def create_machine(self, name, image=None, server=CR_SERVER,
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
        LOG.info("Registering Docker machine [%s::%s] for [%s] at [%s]" %
                 (name, image, CR_SERVER, self.server_address))
        # cmd = PROVISION % dict(server=server,
        #                        name=name,
        #                        api_key=self.api_key)
        env = ["SERVER_ID=%s" % CR_SERVER, "ORG_ID=%s" % self.api_key]
        json_data = dict(Hostname=name, Image=image, Env=env,
                         ExposedPorts=ports, Privileged=privileged,
                         Volumes=volumes,
                         Tty=True,
                         OpenStdin=True,)
        # Cmd=[cmd],
        # Entrypoint=['/bin/curl'])
        create_url = "https://%s/containers/create" % self.server_address

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
            start_url = "https://%s/containers/%s/start" % (
                self.server_address,
                server_id)
            res = requests.post(start_url, data=json.dumps({"Detach": False,
                                                            "Tty": False}),
                                cert=(self._cert_path,
                                      self._key_path),
                                headers=HEADERS,
                                verify=False)
            meta = dict(server_address=self.server_address)
        except Exception, ex:
            LOG.exception(ex)
            raise
        finally:
            self._cleanup()

        return self.OK, server_ids, meta

    def delete_machine(self, server_ids, **kwargs):
        ret = self.OK
        for server_id in server_ids:
            delete_url = "https://%s/containers/%s?force=true" % (
                self.server_address, server_id)
            res = requests.delete(delete_url, cert=(self._cert_path,
                                                    self._key_path),
                                  headers=HEADERS,
                                  verify=False)
            if res.status_code >= 300:
                LOG.error("FAILURE %s(%s)" % (res.status_code, res.content))
                ret = self.FAIL
        return ret
