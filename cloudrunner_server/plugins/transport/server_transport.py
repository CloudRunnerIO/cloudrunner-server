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
from multiprocessing import Process
import os
import signal
import stat
import sys
from threading import Thread
import time
import uuid
import zmq
from zmq.eventloop import ioloop

from cloudrunner.core.message import *
from cloudrunner_server.plugins.transport.tlszmq import TLSZmqServerSocket
from cloudrunner_server.plugins.transport.tlszmq import TLSServerCrypt

LOG = logging.getLogger('ZMQ Transport')
LOGD = logging.getLogger('ZMQ Dispatcher')
LOGR = logging.getLogger('ZMQ ROUTER')
LOGH = logging.getLogger('HEARTBEAT')
LOGA = logging.getLogger('ZMQ ADMIN TOWER')
DEFAULT_ORG = "DEFAULT"


class Transport(object):

    def __init__(self, config):
        Transport.reply_to_node_uri = "ipc://%(sock_dir)s/node-reply.sock" % \
            config
        Transport.msg_bus_uri = "ipc://%(sock_dir)s/control.sock" % config
        Transport.mngmt_uri = "ipc://%(sock_dir)s/pub-management.sock" % config
        Transport.notify_msg_bus_uri = \
            "ipc://%(sock_dir)s/notify-sessions.sock" % config
        Transport.DEFAULT_ORG = DEFAULT_ORG
        self.config = config
        self.publisher = Dispatcher(self.config)
        #self.admin = Admin(self.config)
        #self.router = Router(self.config)

    def run(self):
        pass #self.router.start()

    def shutdown(self):
        LOG.info('Stopping transport')
        #self.admin.terminate()
        #self.publisher.terminate()
        #self.router.terminate()
        LOG.info('Transport stopped')


class Dispatcher(Process):

    """
        Dispatches commands to nodes
    """

    def __init__(self, config):
        super(Dispatcher, self).__init__()
        #self.msg_bus_uri = Transport.msg_bus_uri
        #self.out_msg_bus_uri = Transport.reply_to_node_uri
        self.master_pub_uri = 'tcp://%s' % config.master_pub
        self.pub_listener_uri = "ipc://%(sock_dir)s/pub-proxy.sock" % config
        self.crypter = TLSServerCrypt(config.security.server_key,
                                      cert_password=config.security.cert_pass)
        self.config = config
        self.jobs = {}
        self.session_context = zmq.Context(3)
        self.organizations = []

    @property
    def pub_sock(self):
        """
        Late connect to XPUB socket
        """
        try:
            return self._pub_sock
        except AttributeError:
            self._pub_sock = self.session_context.socket(zmq.PUB)
            self._pub_sock.connect(self.pub_listener_uri)
            time.sleep(.5)
            return self._pub_sock

    def publish(self, tenant_id, *frames):
        # Sign the packet with Master cert
        # ToDo: Since we send with private_encrypt, ensure message size is not
        # greater than the key size. Otherwise - split the message to chunks
        signed_packets = self.crypter.encrypt(*frames)
        self.pub_sock.send_multipart([str(tenant_id), signed_packets])

    def node_reply_queue(self):
        try:
            # Late bind/connect
            return self._node_reply_queue
        except AttributeError:
            self._node_reply_queue = self.session_context.socket(zmq.DEALER)
            self._node_reply_queue.connect(self.out_msg_bus_uri)
            return self._node_reply_queue

    def create_job(self, job_id, event):
        """
        Creates a Job object to send/receive data to/from nodes
        """

        class Job(object):

            def __init__(
                self, job_id, context, msg_bus_uri, admin_msg_bus_uri,
                node_reply_queue, crypter, event):
                self.context = context
                self.crypter = crypter
                self.job_id = job_id
                self.resp_endpoint = self.context.socket(zmq.DEALER)
                self.resp_endpoint.setsockopt(zmq.IDENTITY, job_id)
                self.resp_endpoint.connect(msg_bus_uri)
                self.resp_endpoint.connect(admin_msg_bus_uri)
                self.node_reply_queue = node_reply_queue()
                self.event = event
                self.to_send = []

            def reply(self, *frames):
                frames = list(frames)
                # Inject job id
                frames.insert(2, self.job_id)
                LOGD.info("Reply to [%s] %s" % (frames[1], job_id))
                #self.to_send.append([str(f) for f in frames])
                self.node_reply_queue.send_multipart([str(f) for f in frames])

            def receive(self):
                while not self.event.is_set():
                    try:
                        # if self.to_send:
                        #    packets = self.to_send.pop(0)
                        if self.resp_endpoint.poll(100):
                            rep = self.resp_endpoint.recv_multipart(
                                zmq.NOBLOCK)
                            yield rep
                        else:
                            yield None
                        if not self.event.is_set():
                            return
                    except zmq.ZMQError as e:
                        if hasattr(e, 'errno'):
                            if e.errno == zmq.ETERM:
                                # Context is terminated, exit
                                resp_endpoint.close()
                                return
                        if e.errno == 88:
                            # invalid socket
                            LOGD.warn(str(e))
                            return
                        raise
                    except Exception, ex:
                        LOGD.exception(ex)
                        if hasattr(ex, 'errno') and ex.errno == zmq.ETERM:
                            # Context is terminated, exit
                            resp_endpoint.close()
                        return

                self.destroy()

            def destroy(self):
                self.resp_endpoint.close()

        job = Job(
            job_id, self.session_context, self.msg_bus_uri,
            Transport.notify_msg_bus_uri,
            self.node_reply_queue, self.crypter, event)

        self.jobs[job_id] = job

        LOGD.info("Job %s started, total jobs: %s" %
                 (job_id, len(self.jobs)))

        return job

    def destroy_job(self, job_id):
        if job_id in self.jobs:
            job = self.jobs.pop(job_id)
            job.destroy()

    def destroy_jobs(self):
        LOGD.info("Stopping Publisher's jobs: %s" % self.jobs)
        for k in self.jobs.keys():
            job = self.jobs.pop(k)
            job.destroy()
        if hasattr(self, '_node_reply_queue'):
            self._node_reply_queue.close()
        if hasattr(self, 'session_context'):
            # Force destroy session context
            self.session_context.destroy()

    class Tenants(object):

        class Node(object):

            def __init__(self, name):
                self.created = time.time()
                self.name = name

            @property
            def last_seen(self):
                return time.time() - self.created

            def __eq__(self, name):
                return self.name == name

        def __init__(self, _id, name):
            self.id = _id
            self.name = str(name)
            self.nodes = []

        def __delitem__(self, node_id):
            if node_id in self.nodes:
                self.nodes.remove(node_id)

        def __repr__(self):
            _repr = '[%s]\n' % self.id
            for node in self.nodes:
                _repr = "%s%s\tLast seen: %.f sec ago\n" % (_repr, node.name,
                                                            node.last_seen)
            return _repr

        def __eq__(self, _id):
            return self.id == _id

        def push(self, node):
            if node not in self.nodes:
                self.nodes.append(Dispatcher.Tenants.Node(node))
            else:
                self.nodes[self.nodes.index(node)].created = time.time()

    def heartbeat_handler(self, ident, peer, org):
        tenant = self.tenants.get(org, None)
        if tenant:
            self.tenants[org].push(peer)
            return tenant.id
        else:
            LOG.error("Unrecognized node %s" % peer)

    def multi_ca_broker(self):
        xsub_listener = self.context.socket(zmq.XSUB)
        xsub_listener.bind(self.pub_listener_uri)
        xpub_listener = self.context.socket(zmq.XPUB)
        xpub_listener.bind(self.master_pub_uri)

        heartbeat = self.context.socket(zmq.DEALER)
        heartbeat.setsockopt(zmq.IDENTITY, HEARTBEAT)
        heartbeat.connect(self.msg_bus_uri)

        poller = zmq.Poller()
        poller.register(heartbeat, zmq.POLLIN)
        poller.register(xpub_listener, zmq.POLLIN)
        poller.register(xsub_listener, zmq.POLLIN)

        # Subscribe upstream for all feeds
        xsub_listener.send('\x01')

        # Populate tenants
        for name, uid, _ in self.organizations:
            self.tenants[name] = Dispatcher.Tenants(
                str(uid), name)

        while True:
            try:
                socks = dict(poller.poll(300))
                if xpub_listener in socks:
                    packet = xpub_listener.recv_multipart()
                    action = packet[0][0]
                    target = packet[0][1:]
                    if action == b'\x01':
                        if not target:
                            # Empty target
                            continue
                        LOGH.info('Node started listening to %s' % target)
                        if target not in self.tenants.values():
                            # Send welcome message
                            xpub_listener.send_multipart([target,
                                                          StatusCodes.WELCOME])
                    elif action == b'\x00':
                        # Node de-registered
                        LOGH.info('Node stopped listening to %s' %
                                  target)
                        if target in self.tenants.values():
                            # Active node dropped,
                            # force tenant nodes to reload
                            for tenant in self.tenants.values():
                                if tenant == target:
                                    LOGH.info("Node dropped from %s, " %
                                              tenant.name)
                                    break
                                # xpub_listener.send_multipart(
                                #    [target, StatusCodes.RELOAD])
                    # if packet != [b'\x00']:
                    #    xsub_listener.send_multipart(packet)
                if heartbeat in socks:
                    packet = heartbeat.recv_multipart()
                    req = HeartBeatReq.build(*packet)
                    if not req:
                        LOGH.info("Invalid request: %s" % packet)
                        continue

                    LOGH.debug("Heartbeat from: %s [%s]" % (req.peer, req.org))
                    if req.org not in self.tenants:
                        # Unknown org?
                        LOGH.error("Unknown ORG received %s" % req.org)
                        continue
                    tenant_id = self.heartbeat_handler(req.ident,
                                                       req.peer,
                                                       req.org)
                    if tenant_id and req.control == 'IDENT':
                        self.node_reply_queue_sock.send_multipart([req.ident,
                                                                   req.peer,
                                                                   "SUB_LOC",
                                                                   tenant_id])

                if xsub_listener in socks:
                    packet = xsub_listener.recv_multipart()
                    if packet[1] == 'HB':
                        xpub_listener.send_multipart(packet)
                        continue

                    org_name = packet.pop(0)
                    # Translate org_name to org_uid
                    try:
                        org_uid = self.tenants[org_name].id
                        packet.insert(0, org_uid)
                    except:
                        LOG.error("Problem dispatching to tenant %s."
                                  "Restart of nodes might be needed" %
                                  org_name)
                        continue
                    xpub_listener.send_multipart(packet)

            except zmq.ZMQError as e:
                if hasattr(e, 'errno'):
                    if e.errno == zmq.ETERM:
                        # Context is terminated, exit
                        break
                    if e.errno == 88:
                        # invalid socket, probably closed?
                        break
                raise

        xpub_listener.close()
        xsub_listener.close()
        heartbeat.close()

    def single_ca_broker(self):
        xsub_listener = self.context.socket(zmq.XSUB)
        xsub_listener.bind(self.pub_listener_uri)
        xpub_listener = self.context.socket(zmq.XPUB)
        xpub_listener.bind(self.master_pub_uri)

        heartbeat = self.context.socket(zmq.DEALER)
        heartbeat.setsockopt(zmq.IDENTITY, HEARTBEAT)
        heartbeat.connect(self.msg_bus_uri)

        poller = zmq.Poller()
        poller.register(xpub_listener, zmq.POLLIN)
        poller.register(xsub_listener, zmq.POLLIN)
        poller.register(heartbeat, zmq.POLLIN)

        xsub_listener.send('\x01')
        self.tenants[DEFAULT_ORG] = Dispatcher.Tenants(DEFAULT_ORG,
                                                       "CloudRunner")
        while True:
            try:
                socks = dict(poller.poll(300))
                if xpub_listener in socks:
                    packet = xpub_listener.recv_multipart()
                    action = packet[0][0]
                    target = packet[0][1:]
                    if action == b'\x01':
                        if not target:
                            # Empty target
                            continue
                        LOGH.info('Node started listening to %s' % target)
                        if target != DEFAULT_ORG:
                            # Send welcome message
                            xpub_listener.send_multipart([target,
                                                          StatusCodes.WELCOME])
                    elif action == b'\x00':
                        # Node de-registered
                        LOGH.info('Node stopped listening to %s' %
                                  target)
                    # if packet != [b'\x00']:
                    #    xsub_listener.send_multipart(packet)
                if heartbeat in socks:
                    packet = heartbeat.recv_multipart()
                    req = HeartBeatReq.build(*packet)
                    if not req:
                        LOGH.info("Invalid request: %s" % packet)
                        continue

                    if req.peer == '_master_':
                        self.node_reply_queue_sock.send_multipart([req.ident,
                                                                   req.peer,
                                                                   "NODES",
                                                                   DEFAULT_ORG])
                        continue
                    LOGH.debug("Heartbeat from: %s" % req.peer)
                    self.heartbeat_handler(req.ident, req.peer, DEFAULT_ORG)
                    if req.control == 'IDENT':
                        self.node_reply_queue_sock.send_multipart([req.ident,
                                                                   req.peer,
                                                                   "SUB_LOC",
                                                                   DEFAULT_ORG])
                if xsub_listener in socks:
                    packet = xsub_listener.recv_multipart()
                    packet[0] = DEFAULT_ORG
                    xpub_listener.send_multipart(packet)

            except zmq.ZMQError as e:
                if hasattr(e, 'errno'):
                    if e.errno == zmq.ETERM:
                        # Context is terminated, exit
                        break
                    if e.errno == 88:
                        # invalid socket, probably closed?
                        break
                raise

        xpub_listener.close()
        xsub_listener.close()
        heartbeat.close()

    def run(self):
        """ Start Response router """
        self.context = zmq.Context(3)

        self.tenants = {}

        if self.config.security.use_org:
            Thread(target=self.multi_ca_broker).start()
        else:
            Thread(target=self.single_ca_broker).start()

        from cloudrunner.util.shell import Timer

        self.HEARTBEAT_INTERVAL = int(self.config.heartbeat_interval or 60)

        signal.signal(signal.SIGINT, self.close)
        signal.signal(signal.SIGTERM, self.close)
        signal.signal(signal.SIGHUP, self.heartbeat)

        LOGH.info("HEARTBEAT thread: %s, "
                  "interval: %s" % (os.getpid(), self.HEARTBEAT_INTERVAL))

        self.node_reply_queue_sock = self.context.socket(zmq.DEALER)
        self.node_reply_queue_sock.connect(self.out_msg_bus_uri)
        self.publ_management = self.context.socket(zmq.PUB)
        self.publ_management.bind(Transport.mngmt_uri)

        timer = Timer(self.HEARTBEAT_INTERVAL, self.heartbeat_call)
        timer.start()

        #ioloop.IOLoop.instance().start()
        self.node_reply_queue_sock.close()
        self.publ_management.close()
        timer.stop()

    def heartbeat_call(self):
        # clear dropped nodes
        for tenant in self.tenants.values():
            for node in tenant.nodes:
                if node.last_seen > 1.5 * self.HEARTBEAT_INTERVAL:
                    # Node dropped?
                    LOGH.info("Dropping node %s due to inactivity" %
                              node.name)
                    tenant.nodes.remove(node)
            self.pub_sock.send_multipart([tenant.id, StatusCodes.HB])

    def heartbeat(self, *args):
        # Print current tenants map in console(invoked from service using HUP)
        sys.stdout.write(str(self.tenants))
        nodes = []
        for tenant in self.tenants.values():
            nodes.extend([node.name for node in tenant.nodes
                          if node.last_seen < self.HEARTBEAT_INTERVAL])
        self.publ_management.send_multipart([tenant.name] + nodes)

    def close(self, *args):
        LOGD.info("Stopping Publisher Process")
        #self.context.destroy()
        ioloop.IOLoop.instance().stop()
        LOGD.info("Stopped Publisher Process")


class Router(Process):

    """
        Receives and routes data from nodes to clients and back
    """

    def __init__(self, config):
        super(Router, self).__init__()
        #self.repl_uri = 'tcp://%s' % config.master_repl
        self.sock_dir = config.sock_dir
        self.msg_bus_uri = Transport.msg_bus_uri
        self.out_msg_bus_uri = Transport.reply_to_node_uri
        self.ssl_worker_uri = "inproc:///ssl-worker-sock"

        self.config = config
        self.process = lambda packet: ['Receiver.process not implemented']

    def run(self):
        """ Run response processing thread """
        self.context = zmq.Context(3)
        # Socket to receive replies
        self.repl_sock = self.context.socket(zmq.ROUTER)

        self.repl_sock.bind(self.repl_uri)
        signal.signal(signal.SIGINT, self.close)
        signal.signal(signal.SIGTERM, self.close)

        def router_worker(context, msg_bus_uri, out_msg_bus_uri,
                          ssl_worker_uri):
            try:
                router = context.socket(zmq.ROUTER)
                router.bind(msg_bus_uri)
            except zmq.ZMQError, zerr:
                if zerr.errno == 2:
                    # Socket dir is missing
                    LOGR.error("Socket uri is missing: %s" % msg_bus_uri)

            reply_router = context.socket(zmq.DEALER)
            reply_router.bind(out_msg_bus_uri)

            ssl_worker = context.socket(zmq.DEALER)
            ssl_worker.bind(ssl_worker_uri)

            poller = zmq.Poller()
            poller.register(reply_router, zmq.POLLIN)
            poller.register(ssl_worker, zmq.POLLIN)

            socks = {}
            time.sleep(1)  # wait for 1 sec for sockets to come up
            while True:
                try:
                    socks = dict(poller.poll())
                except zmq.ZMQError, zerr:
                    if zerr.errno == zmq.ETERM:
                        # Context terminated, exit
                        break
                try:
                    if ssl_worker in socks:
                        packets = ssl_worker.recv_multipart()
                        req = ClientReq.build(*packets)
                        if not req:
                            LOGR.error(
                                "Invalid request from Client %s" % packets)
                            continue
                        if req.dest == HEARTBEAT:
                            LOGR.debug('Router received: %s' % req)
                        else:
                            LOGR.info('Router received: %s' % req)

                        if not req.peer and req.dest != ADMIN_TOWER:
                            # Anonymous accessing data feed
                            LOGR.error('NOT AUTHORIZED: %s : %s' % (req.peer,
                                                                    req.dest))
                            continue
                        router.send_multipart(
                            RerouteReq(req).pack())

                    elif reply_router in socks:
                        packets = reply_router.recv_multipart()
                        rep = ClientRep.build(*packets)
                        if not rep:
                            LOGR.error("Invalid reply received: %s" % packets)
                            continue
                        rep_packet = rep.pack()
                        LOGR.info("Router reply: %s" % rep_packet[:2])
                        ssl_worker.send_multipart(rep_packet)
                except zmq.ZMQError, zerr:
                    if zerr.errno == zmq.ETERM or zerr.errno == zmq.ENOTSUP \
                        or zerr.errno == zmq.ENOTSOCK:
                        break
            LOGR.info("Exited router worker")
            router.close()
            reply_router.close()
            ssl_worker.close()

        Thread(target=router_worker, args=[self.context, self.msg_bus_uri,
                                           self.out_msg_bus_uri,
                                           self.ssl_worker_uri]).start()

        if self.config.security.use_org:
            verify_loc = []
            ca_path = os.path.dirname(os.path.abspath(self.config.security.ca))
            verify_loc.append(self.config.security.ca)
            org_dir = os.path.join(ca_path, 'org')
            for (dir, _, files) in os.walk(org_dir):
                for _file in files:
                    if _file.endswith('.ca.crt'):
                        verify_loc.append(os.path.join(dir, _file))
        else:
            verify_loc = self.config.security.ca

        self.master_repl = TLSZmqServerSocket(
            self.repl_sock,
            self.ssl_worker_uri,
            self.config.security.server_cert,
            self.config.security.server_key,
            self.config.security.ca,
            verify_loc=verify_loc,
            cert_password=self.config.security.cert_pass)

        def master(master_repl):
            while True:
                try:
                    master_repl.start()  # Start TLS ZMQ server socket
                except zmq.ZMQError, err:
                    if getattr(err, 'errno', 0) == zmq.ETERM:
                        # System interrupt
                        break
                except KeyboardInterrupt:
                    break
                except Exception, ex:
                    LOGR.exception(ex)
                    if getattr(ex, 'errno', 0) == zmq.ETERM:
                        break
        Thread(target=master, args=[self.master_repl]).start()

        #ioloop.IOLoop.instance().start()

    def close(self, *args):
        LOGR.info("Stopping router")
        self.repl_sock.close(10)
        self.master_repl.terminate()
        self.context.destroy()
        ioloop.IOLoop.instance().stop()
        LOGR.info("Stopped router")
