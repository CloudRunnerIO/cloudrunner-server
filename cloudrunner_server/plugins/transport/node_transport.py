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

import json
import logging
import M2Crypto as m
import os
import signal
import stat
from threading import Thread
from threading import Event
import time
import zmq
from zmq.eventloop import ioloop
import uuid

from cloudrunner.core.message import *
from cloudrunner.util.shell import colors
from cloudrunner_server.plugins.transport.tlszmq import \
    (ConnectionException, ServerDisconnectedException,
     TLSZmqClientSocket, TLSClientDecrypt)

LOGC = logging.getLogger('ZMQ Node Transport')
STATE_OPS = ("IDENT", "RELOAD", 'FINISHED')


class Transport(object):

    _ssl_sock = None

    def __init__(self, config, master_sub_uri, master_reply_uri,
                 node_queue_uri, **kwargs):
        self.config = config
        self.node_id = config.id
        self.master_sub = 'tcp://%s' % master_sub_uri
        self.master_reply_uri = 'tcp://%s' % master_reply_uri
        self.worker_uri = node_queue_uri
        self.wait_for_approval = int(kwargs.get('wait_for_approval', 120))
        self.ssl_thread_event = Event()
        # Prepare zmq context for SSL

    def ssl_socket_device(self, context):
        LOGC.info("Starting new SSL thread")
        args = []
        kwargs = {}
        if self.config.security.node_cert and \
                os.path.exists(self.config.security.node_cert):
            # We have issued certificate
            args.append(self.config.security.node_cert)
            args.append(self.config.security.node_key)
            kwargs['ca'] = self.config.security.ca
            kwargs['cert_password'] = self.config.security.cert_pass

        ssl_socket = TLSZmqClientSocket(context, self.master_reply_uri,
                                        self.worker_uri, self.ssl_thread_event,
                                        *args, **kwargs)
        ssl_socket.start()

        ssl_socket.shutdown()
        LOGC.info("Exiting SSL thread")


    class Listener(Thread):

        def __init__(self, context, sub_uri, callback, identify,
                     decrypter, config):
            super(Transport.Listener, self).__init__()
            self.context = context
            self.sub_uri = sub_uri
            self.callback = callback
            self.identify = identify
            self.decrypter = decrypter
            self.config = config

        def run(self):
            # Try to subscribe using Tenant data
            self.sub = str(uuid.uuid1())
            self.sub_sock = self.context.socket(zmq.SUB)
            self.sub_sock.setsockopt(zmq.SUBSCRIBE, self.sub)
            self.sub_sock.connect(self.sub_uri)

            while True:
                try:
                    fff = self.sub_sock.recv_multipart()
                    _, message = fff
                    if message == StatusCodes.WELCOME or \
                        message == StatusCodes.RELOAD:
                        # Heartbeat
                        subscribe_topic = self.identify()
                        if subscribe_topic:
                            self.sub_sock.setsockopt(
                                zmq.UNSUBSCRIBE, self.sub)
                            self.sub = subscribe_topic[0]
                            self.sub_sock.setsockopt(zmq.SUBSCRIBE, self.sub)
                            LOGC.info("Subscribed to tenant topic %s" %
                                      self.sub)
                        continue
                    elif message == StatusCodes.HB:
                        # Heartbeat
                        self.callback(message)
                    else:
                        try:
                            frames = self.decrypter.decrypt(message)
                        except Exception, ex:
                            LOGC.error("Cannot decrypt frames from [%s]: %r" %
                                      (_, ex))
                        try:
                            print "FRAMES", frames

                            self.callback(*frames)
                        except Exception, ex:
                            LOGC.error("Cannot pass job to agent: %r" % ex)
                except KeyboardInterrupt:
                    LOGC.info('Exiting node listener thread')
                    break
                except zmq.ZMQError, zerr:
                    if zerr.errno == zmq.ETERM or zerr.errno == zmq.ENOTSUP \
                        or zerr.errno == zmq.ENOTSOCK:
                        break
                    LOGC.exception(zerr)
                    LOGC.error(zerr.errno)
                except ValueError, ex: #Exception, ex:
                    LOGC.error("Node listener thread: exception %r" % ex)

            self.sub_sock.close(0)
            LOGC.info('Node Listener exited')

    def run(self, context, callback, identify, num_threads=5):
        # Run main SUB thread to listen to Master

        if not os.path.exists(self.config.security.node_key):
            LOGC.warn('Client key not generated, run program '
                      'with "configure" option first.')
            exit(1)

        if not os.path.exists(self.config.security.node_cert):
            csreq = self.config.security.node_csr
            if not csreq:
                base_name = self.config.security.node_key.rpartition('.')[0]
                csreq = '.'.join(base_name, ".csr")
                if not os.path.exists(csreq):
                    LOGC.warn('Client certificate request not found.'
                              'Run program with "configure" option first or set'
                              ' the path to the .csr file in the config as:\n'
                              '[Security]\n'
                              'node_csr=path_to_file\n')
                    exit(1)

            if not self._register(context):
                return -1

        self.decrypter = TLSClientDecrypt(self.config.security.server)
        self.context = context

        # Start SSL thread
        self.ssl_start()

        # Run worker threads
        self.listeners = []

        listener = Transport.Listener(self.context, self.master_sub,
                                      callback, identify,
                                      self.decrypter, self.config)
        listener.start()

    def ssl_stop(self):
        self.ssl_thread_event.set()
        self.ssl_thread.join(1)
        self.ssl_thread_event.clear()

    def ssl_start(self):
        self.ssl_thread = Thread(target=self.ssl_socket_device,
                                 args=[self.context])
        self.ssl_thread.start()

    def restart(self):
        LOGC.info('Restarting SSL Client')
        self.ssl_stop()
        self.ssl_start()
        LOGC.info('SSL Client restarted')

    def shutdown(self):
        LOGC.info("Received terminate signal")
        self.ssl_stop()
        LOGC.info('Node transport closed')
