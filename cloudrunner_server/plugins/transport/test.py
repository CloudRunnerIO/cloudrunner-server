#!/usr/bin/python
# -*- coding: utf-8 -*-
# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2013 CloudRunner.IO
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from cloudrunner.util.config import Config
import json
import logging
from threading import Thread
import zmq

logging.basicConfig(format='%(name)s :: %(levelname)s :: %(message)s',
                    level=logging.INFO)
from cloudrunner import CONFIG_LOCATION, CONFIG_NODE_LOCATION
from cloudrunner.plugins.transport.tlszmq import TLSZmqServerSocket
from cloudrunner.plugins.transport.tlszmq import TLSZmqClientSocket

CONFIG = Config(CONFIG_LOCATION)
CONFIG_NODE = Config(CONFIG_NODE_LOCATION)


def Main():
    ctx = zmq.Context(1)
    main_sock = ctx.socket(zmq.ROUTER)
    main_sock.bind('tcp://0.0.0.0:5999')
    client_sock = ctx.socket(zmq.DEALER)
    client_sock.connect('tcp://0.0.0.0:5999')

    endpoint = ctx.socket(zmq.DEALER)
    endpoint.setsockopt(zmq.IDENTITY, 'dummy0')
    endpoint.bind('ipc:///tmp/endp.sock')
    router = ctx.socket(zmq.ROUTER)
    router.connect('ipc:///tmp/endp.sock')

    def master_listen(main_sock):
        def put_data(peer, packet, sender=None, org=None):
            pass #print peer, packet

        def get_data(node_id, sender=None, org=None):
            return sender, iter([json.dumps(['DUMMY REP'])])

        master = TLSZmqServerSocket(main_sock,
                                    CONFIG.security.server_cert,
                                    CONFIG.security.server_key,
                                    CONFIG.security.ca,
                                    verify_loc=CONFIG.security.ca,
                                    cert_password=CONFIG.security.cert_pass)
        master.set_send_recv_callback(put_data, get_data)
        master.start()

    def endpoint_recv(endp):
        try:
            frames = endp.recv_multipart()
        except zmq.ZMQError, zerr:
            return
        cmd = json.loads(frames[2])
        if 'READY' in cmd:
            endp.send_multipart(['uuid', 'task'])
        else:
            endp.send_multipart(['uuid', 'OK'])
        task_result = endp.recv_multipart()
        endp.send_multipart(['uuid', 'OK'])

    master_t = Thread(target=master_listen, args=(main_sock,))

    endpoint_t = Thread(target=endpoint_recv, args=(endpoint,))

    master_t.start()
    endpoint_t.start()

    ssl_client = TLSZmqClientSocket(client_sock,
                                    CONFIG_NODE.security.node_cert,
                                    CONFIG_NODE.security.node_key,
                                    ca=CONFIG_NODE.security.ca,
                                    cert_password=CONFIG_NODE.security.cert_pass)

    def parse_result(ret):
        packets = ret.split('\x00')
        for packet in packets:
            logging.info("SSL Client recv: %s" % (packet))

    ret = ssl_client.send_recv(json.dumps(['dummy0', "READY", '{}']))
    parse_result(ret)

    ret = ssl_client.send_recv(json.dumps(['dummy0', 'FINISHED',
                                           '{}']))
    parse_result(ret)
    logging.info("TASK FINISHED")

    ssl_client.shutdown()
    ctx.destroy()

if __name__ == '__main__':
    Main()
