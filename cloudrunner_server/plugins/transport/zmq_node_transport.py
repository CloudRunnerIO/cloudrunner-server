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

import logging
import zmq
from zmq.eventloop import ioloop

from cloudrunner.core.message import (ADMIN_TOWER, HEARTBEAT)
from cloudrunner.core.exceptions import ConnectionError
from cloudrunner.plugins.transport.base import TransportBackend
from cloudrunner import VAR_DIR

from .tlszmq import \
    (ConnectionException, ServerDisconnectedException,
     TLSZmqClientSocket, TLSClientDecrypt)

from cloudrunner.plugins.transport.zmq_transport import (SockWrapper,
                                                         PollerWrapper)
LOGC = logging.getLogger('Plain Node Transport')
STATE_OPS = ("IDENT", "RELOAD", 'FINISHED')


class NodeTransport(TransportBackend):

    proto = 'zmq+ssl'

    def __init__(self, config, **kwargs):
        self.config = config
        self.node_id = config.id
        self.wait_for_approval = int(kwargs.get('wait_for_approval', 120))
        self._sockets = []
        self.context = zmq.Context()
        self.ssl_thread_event = Event()

    def loop(self):
        ioloop.IOLoop.instance().start()

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

        ssl_socket = TLSZmqClientSocket(self.context,
                                        self.buses['jobs'][0],
                                        self.endpoints['ssl-proxy'],
                                        self.ssl_thread_event,
                                        *args, **kwargs)
        ssl_socket.start()

        ssl_socket.shutdown()
        LOGC.info("Exiting SSL thread")

    def prepare(self):
        LOGC.debug("Starting ZMQ Transport")

        # check in order: args, kwargs, config
        master_sub = 'tcp://%s' % self.config.master_pub
        master_reply_uri = 'tcp://%s' % self.config.master_repl
        worker_count = int(self.config.worker_count or 5)

        sock_dir = self.config.sock_dir or os.path.join(VAR_DIR,
                                                        'cloudrunner', 'sock')
        if not os.path.exists(sock_dir):
            os.makedirs(sock_dir)

        if os.name == 'nt':
            control_uri = 'tcp://127.0.0.1:54112'
            ssl_proxy_uri = 'tcp://127.0.0.1:54112'
        else:
            control_uri = 'inproc://control-queue.sock'
            #control_uri = 'ipc://%s/control-queue.sock' % sock_dir
            ssl_proxy_uri = 'inproc://ssl-proxy-queue.sock'
            ssl_proxy_uri = 'ipc://%s/ssl-proxy-queue.sock' % sock_dir

        self.endpoints = {'ssl-proxy': ssl_proxy_uri}
        self.buses = {
            'requests': [master_sub, control_uri],
            'jobs': [master_reply_uri, ssl_proxy_uri],
        }

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

            self.ssl_start()
            if not self._register():
                LOGC.error("Cannot register node at master")
                return False
            self.ssl_stop()

        # Run worker threads
        if self.config.mode == 'single-user':
            LOGC.info('Running client in single-user mode')
        else:
            LOGC.info('Running client in server mode')
            listener = Thread(target=self.listener_device)
            listener.start()

        self.ssl_start()
        self.decrypter = TLSClientDecrypt(self.config.security.server)

        return True

    def consume_queue(self, endp_type, ident=None, *args, **kwargs):
        if endp_type not in self.buses:
            raise Exception("Invalid queue type: %s" % endp_type)
        uri = self.buses[endp_type][1]
        try:
            sock = self.context.socket(zmq.DEALER)
            if ident:
                sock.setsockopt(zmq.IDENTITY, ident)
            sock.connect(uri)

        except zmq.ZMQError, zerr:
            if getattr(zerr, 'errno', 0) == 93:
                # wrong protocol
                raise Exception(
                    "Wrong connection uri: %s" % uri)
            if getattr(zerr, 'errno', 0) == 2:
                # wrong protocol
                raise Exception("Socket uri is not accessible: %s" %
                                uri)
            else:
                console.red(zerr)

        wrap = SockWrapper(uri, sock)
        self._sockets.append(wrap)
        return wrap

    publish_queue = consume_queue

    def create_poller(self, *sockets):
        return PollerWrapper(*sockets)

    def listener_device(self):
        self.sub = str(uuid.uuid1())
        master_sub = self.context.socket(zmq.SUB)
        master_sub.setsockopt(zmq.SUBSCRIBE, self.sub)
        master_sub.connect(self.buses['requests'][0])

        dispatcher = self.context.socket(zmq.DEALER)
        dispatcher.bind(self.buses['requests'][1])

        ssl_proxy = self.context.socket(zmq.DEALER)
        ssl_proxy.setsockopt(zmq.IDENTITY, 'SUB_LOC')
        ssl_proxy.connect(self.endpoints['ssl-proxy'])

        poller = zmq.Poller()
        poller.register(master_sub, zmq.POLLIN)
        poller.register(ssl_proxy, zmq.POLLIN)
        # Sindicate requests from two endpoints and forward to 'requests'
        while True:
            try:
                ready = dict(poller.poll(100))
                if master_sub in ready:
                    _, message = master_sub.recv_multipart()
                    if message:
                        #message = frames[0]
                        if message == StatusCodes.WELCOME or \
                            message == StatusCodes.RELOAD:
                            ssl_proxy.send_multipart([HEARTBEAT,
                                                      'IDENT'])
                        elif message == StatusCodes.HB:
                            # Heartbeat
                            ssl_proxy.send_multipart([HEARTBEAT,
                                                      self.node_id])
                        else:
                            # decrypt
                            try:
                                msg = self.decrypter.decrypt(message)
                                dispatcher.send_multipart(
                                    [str(m) for m in msg])
                            except Exception, ex:
                                LOGC.error(
                                    "Cannot decrypt frames from [%s]: %r" %
                                    (_, ex))
                if ssl_proxy in ready:
                    frames = ssl_proxy.recv_multipart()
                    if len(frames) == 2:
                        # ToDo: better command handler
                        master_sub.setsockopt(zmq.UNSUBSCRIBE, self.sub)
                        self.sub = frames[0]
                        master_sub.setsockopt(zmq.SUBSCRIBE, self.sub)
                        LOGC.info("Subscribed to topic %s" % self.sub)
                    else:
                        dispatcher.send_multipart(frames)
            except KeyboardInterrupt:
                LOGC.info('Exiting node listener thread')
                break
            except zmq.ZMQError, zerr:
                if zerr.errno == zmq.ETERM or zerr.errno == zmq.ENOTSUP \
                    or zerr.errno == zmq.ENOTSOCK:
                    break
                LOGC.exception(zerr)
                LOGC.error(zerr.errno)
            except Exception, ex:
                LOGC.error("Node listener thread: exception %s" % ex)

        ssl_proxy.close()
        master_sub.close()
        dispatcher.close()
        LOGC.info('Node Listener exited')

    def _register(self):

        LOGC.info(colors.grey('Registering on Master...'))
        csreq = self.config.security.node_csr

        try:
            csreq_data = open(csreq).read()
        except Exception, ex:
            LOGC.error(colors.red('Cannot read %s file' % csreq))
            return False

        try:
            csr = None
            csr = m.X509.load_request(csreq)
            node_id = csr.get_subject().CN
            del csr
        except Exception, ex:
            LOGC.error(
                "%s doesn't seem to be a valid certificate file" % csreq)
            LOGC.exception(ex)
            if csr:
                del csr
            return False

        self.ssl_start()
        start_reg = time.time()

        def _next(reply):
            if not reply:
                # First call? Send CSR
                return [ADMIN_TOWER, 'REGISTER', node_id, csreq_data]

            rp = RegisterRep(reply)

            if rp.reply == "APPROVED":
                # Load certificates from chain
                (node_crt_string,
                 ca_crt_string,
                 server_crt_string) = rp.data.split(
                     TOKEN_SEPARATOR)

                node_cert = m.X509.load_cert_string(
                    str(node_crt_string), m.X509.FORMAT_PEM)
                ca_cert = m.X509.load_cert_string(
                    str(ca_crt_string), m.X509.FORMAT_PEM)
                server_cert = m.X509.load_cert_string(
                    str(server_crt_string), m.X509.FORMAT_PEM)

                # First verify if the cert matches the request
                csr = m.X509.load_request_string(csreq_data)
                node_key_priv = m.RSA.load_key(
                    self.config.security.node_key,
                    lambda x: self.config.security.cert_pass)

                node_key = m.EVP.PKey()
                node_key.assign_rsa(node_key_priv)
                node_cert.set_pubkey(node_key)

                assert csr.verify(node_cert.get_pubkey()), \
                    "Certificate request failed to verify node cert"
                assert node_cert.verify(ca_cert.get_pubkey()), \
                    "Node cert failed to verify CA cert"

                crt_file_name = self.config.security.node_cert
                node_cert.save_pem(crt_file_name)
                os.chmod(crt_file_name, stat.S_IREAD | stat.S_IWRITE)
                del node_key
                del node_cert
                del csr

                if not self.config.security.ca:
                    base = os.path.dirname(os.path.abspath(crt_file_name))
                    self.config.update('Security', 'ca',
                                       os.path.join(base, 'ca.crt'))

                # ca_cert.save_pem(self.config.security.ca)
                open(self.config.security.ca, 'w').write(str(ca_crt_string))

                os.chmod(self.config.security.ca, stat.S_IREAD | stat.S_IWRITE)
                del ca_cert

                if not self.config.security.server:
                    base = os.path.dirname(os.path.abspath(crt_file_name))
                    self.config.update('Security', 'server',
                                       os.path.join(base, 'server.crt'))

                server_cert.save_pem(self.config.security.server)
                os.chmod(self.config.security.server,
                         stat.S_IREAD | stat.S_IWRITE)
                del server_cert

                LOGC.info('Master approved the node. Starting service')
                return 0
            elif rp.reply == "REJECTED":
                if rp.data == 'SEND_CSR':
                    return [ADMIN_TOWER, 'REGISTER', node_id, csreq_data]
                if rp.data == 'PENDING':
                    LOGC.info("Master says: Request queued for approval.")
                    if time.time() < start_reg + int(self.wait_for_approval):
                        time.sleep(10)  # wait 10 sec before next try
                        return [ADMIN_TOWER, 'REGISTER', node_id, csreq_data]
                    else:
                        return -1
                elif rp.data == 'ERR_CRT_EXISTS':
                    LOGC.info('Master says: "There is already an issued certificate'
                              ' for this node. Remove the certificate'
                              ' from master first"')
                    return -1
                elif rp.data == 'ERR_CN_FAIL':
                    LOGC.info(
                        'Master says: "Node Id doesn\'t match the request CN"')
                    return -1
                elif rp.data == 'INV_CSR':
                    LOGC.info('Master says: "Invalid CSR file"')
                    return -1
                elif rp.data == 'ERR_NAME_FORBD':
                    csr = m.X509.load_request_string(csreq_data)
                    LOGC.info('Master says: "The chosen node name(CN) - [%s] is '
                              'forbidden. Choose another one."' %
                              csr.get_subject().CN)
                    del csr
                    return -1
                elif rp.data == 'APPR_FAIL':
                    LOGC.info('Master says: "Certificate approval failed"')
                    return -1
                else:
                    return -1
            else:
                return -1

        reply = None
        approved = False

        reg_sock = self.context.socket(zmq.DEALER)
        reg_sock.setsockopt(zmq.IDENTITY, self.node_id)
        reg_sock.connect(self.endpoints['ssl-proxy'])

        while True:
            try:
                next_rq = _next(reply)
                if next_rq == -1:
                    break
                if next_rq == 0:
                    # We're done, go ahead
                    approved = True
                    break
                else:
                    end_wait = \
                        start_reg + int(self.wait_for_approval) - time.time()
                    reg_sock.send_multipart(next_rq)
                    if not reg_sock.poll(end_wait * 1000):
                        LOGC.error("Timeout waiting for register response")
                        break
                    reply = reg_sock.recv_multipart()
            except ConnectionException:
                LOGC.error("Rebuilding ssl connection %s" % reply)
                self.restart()
                reply = next_rq
            except Exception, ex:
                LOGC.error(ex)
                break

        self.ssl_stop()
        reg_sock.close(0)
        return approved

    def ssl_start(self):
        self.ssl_thread = Thread(target=self.ssl_socket_device,
                                 args=[self.context])
        self.ssl_thread.start()

    def ssl_stop(self):
        self.ssl_thread_event.set()
        self.ssl_thread.join(1)
        self.ssl_thread_event.clear()

    def restart(self):
        LOGC.info('Restarting SSL Client')
        self.ssl_stop()
        self.ssl_start()
        LOGC.info('SSL Client restarted')

    def terminate(self):
        LOGC.info("Received terminate signal")
        self.ssl_stop()
        ioloop.IOLoop.instance().stop()
        for sock in self._sockets:
            sock.close()
        self.context.term()
        LOGC.info('Node transport closed')
