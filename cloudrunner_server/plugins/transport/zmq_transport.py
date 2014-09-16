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

import fcntl
import logging
import M2Crypto as m
import os
from os import path as p
import signal
from socket import gethostname
from threading import Event
from threading import Thread
import time
import zmq
from zmq.eventloop import ioloop

from cloudrunner.util.tlszmq import TLSZmqServerSocket
from cloudrunner.core.message import *  # noqa
from cloudrunner.plugins.transport.zmq_transport import (SockWrapper,
                                                         PollerWrapper)
from cloudrunner.util.aes_crypto import Crypter
from cloudrunner.util.shell import Timer

from cloudrunner_server.plugins.auth.base import NodeVerifier
from cloudrunner_server.plugins.transport.base import (ServerTransportBackend,
                                                       Tenant)
from cloudrunner_server.master.functions import CertController

LOGR = logging.getLogger('ZMQ ROUTER')
LOGA = logging.getLogger('ZMQ ACCESS')
LOGL = logging.getLogger('ZMQ LOGGER')
LOGPUB = logging.getLogger('ZMQ PUBLISH')


LOGL.setLevel(logging.ERROR)


class Pipe(object):

    def __init__(self, publish, consume):
        self.publish = publish
        self.consume = consume


class ZmqTransport(ServerTransportBackend):

    proto = "zmq+ssl"
    managed_sessions = {}

    def __init__(self, config):
        self.preprocessor = []
        self.context = zmq.Context()
        self.bindings = {}
        self.running = Event()
        self._sockets = []
        self.ccont = CertController(config)
        self.host = gethostname().lower()

        self.buses = DictWrapper()

        # node -> server
        self.buses.in_messages = Pipe(
            'inproc://ssl-worker',
            "inproc://in-messages.sock")

        # server -> node
        self.buses.out_messages = Pipe(
            "inproc://out-messages.sock",
            'inproc://ssl-worker',
        )

        # server -> user
        self.buses.finished_jobs = Pipe(
            "inproc://job-done.sock",
            "inproc://disp-workers.sock"
        )

        self.master_pub_uri = 'tcp://%s' % config.master_pub

        self.buses.requests = Pipe(
            'tcp://' + (config.listen_uri or '0.0.0.0:5559'),
            "inproc://request-queue"
        )

        self.buses.replies = Pipe(
            "inproc://request-queue",
            "inproc://replies-queue"
        )

        self.buses.user_input = Pipe(
            "inproc://session-notification-push",
            "inproc://session-notification-pull"
        )

        self.buses.scheduler = Pipe(
            "ipc://%(sock_dir)s/scheduler-push.sock" % config,
            "inproc://scheduler-pull"
        )

        self.buses.logger = Pipe(
            "inproc://logger-queue",
            "inproc://logger-queue-workers",
        )

        self.buses.logger_fwd = Pipe(
            config.logger_uri or (
                "ipc://%(sock_dir)s/logger.sock" % config),
            None
        )

        self.buses.publisher = Pipe(
            "inproc://pub-proxy.sock",
            self.master_pub_uri
        )

        proxy_pub_port = config.proxy_pub_port or 5553

        self.endpoints = {
            'node_reply': 'tcp://%s' % config.master_repl,
            "replicator": "tcp://0.0.0.0:%s" % proxy_pub_port,
            "router_fwd": "ipc://%(sock_dir)s/router-fwd.sock" % config,
            "pub_fwd": "ipc://%(sock_dir)s/pub-fwd.sock" % config
        }

        self.config = config
        self.proxies = {}

        if self.config._config.has_section('Proxy'):
            self.config.add_section('proxy', 'Proxy')
            for (host, proxy) in self.config.proxy.items():
                self.proxies[host] = proxy.strip()

        self.router = Router(self.config, self.context,
                             self.buses, self.endpoints, self.running,
                             self.proxies)
        self.crypter = Crypter()
        self.subca_dir = p.join(
            p.dirname(p.abspath(self.config.security.ca)), 'org')
        self._watch_dir('CD', self.subca_dir, callback=self._cert_changed)

        # Check for crl file
        crl_file = p.join(
            p.dirname(p.abspath(self.config.security.ca)), 'crl')
        if not p.exists(crl_file):
            crl = open(crl_file, 'w')
            crl.write('')
            crl.close()

        self.cert_dir = p.join(
            p.dirname(p.abspath(self.config.security.ca)), 'nodes')
        # Watch deletes, which occur on revoke
        self._watch_dir('D', self.cert_dir, callback=self._nodes_changed)

        # init
        self.heartbeat_timeout = int(self.config.heartbeat_timeout or 30)
        self.tenants = {}
        self._cert_changed()
        self._nodes_changed(wait=False)

    def _watch_dir(self, mode, _dir, callback):
        cert_fd = os.open(_dir, 0)
        fcntl.fcntl(cert_fd, fcntl.F_SETSIG, 0)
        watch_mode = fcntl.DN_MULTISHOT
        if 'C' in mode:
            watch_mode |= fcntl.DN_CREATE
        if 'D' in mode:
            watch_mode |= fcntl.DN_DELETE
        if 'M' in mode:
            watch_mode |= fcntl.DN_MODIFY

        fcntl.fcntl(cert_fd, fcntl.F_NOTIFY, watch_mode)
        signal.signal(signal.SIGIO, callback)

    def _nodes_changed(self, wait=True, *args):

        def read():
            crl_file = p.join(
                p.dirname(p.abspath(self.config.security.ca)), 'crl')
            fd = open(crl_file, 'r')
            CRL_LIST = [line for line in fd.read().split('\n') if line]
            for cert_serial in CRL_LIST:
                try:
                    ser_no = int(cert_serial)
                    if ser_no not in TLSZmqServerSocket.CRL:
                        TLSZmqServerSocket.CRL.append(ser_no)
                except ValueError, er:
                    LOGR.exception(er)

            fd.close()

        if wait:
            time.sleep(1)  # wait 1 sec for file closing
        try:
            read()
        except Exception, ex:
            LOGR.exception(ex)
            # try again...
            time.sleep(2)
            try:
                read()
            except Exception, ex:
                LOGR.exception(ex)

    def _cert_changed(self, *args):
        # Reload certs
        if self.config.security.use_org:
            orgs = [ca[1] for ca in self.ccont.list_ca()]
        else:
            orgs = [DEFAULT_ORG]
        for org in orgs:
            if org not in self.tenants:
                LOGR.warn("Registering tenant %s" % org)
                self.tenants[org] = Tenant(org)
        current_orgs = self.tenants.keys()
        for org in current_orgs:
            if org not in orgs:
                self.tenants.pop(org)

    def _verify_node(self, node, request, **kwargs):
        for verifier in NodeVerifier.__subclasses__():
            if verifier(self.config).verify(node, request):
                return True
        return False

    def _check_cert2req(self, crt_file, req):
        """
        Check the CSR with the issued certificate.
        This checks the case when the node has regenerated its keys,
        and sends a REGISTER request to master, but the Master already has
        signed certificate with a previous request. Also this could be
        the case of an attacker who tries to send a certificate request
        using the name of a attacked node. We *MUST NOT* return the CRT
        in that case, as this will make the node legally approved!
        """
        crt = None
        if not p.exists(crt_file):
            return False, None, None
        try:
            crt = m.X509.load_cert(crt_file)
            subj = crt.get_subject()
            if req.verify(crt.get_pubkey()):
                if self.config.security.use_org:
                    return subj.O, subj.CN, crt.get_serial_number()
                else:
                    return 'DEFAULT', subj.CN, crt.get_serial_number()
            else:
                return False, None, None
        except Exception, ex:
            LOGA.exception(ex)
            return False, None, None
        finally:
            del crt

    def _build_cert_response(self, node, csr_data, crt_file_name):
        csr = None
        try:
            csr = m.X509.load_request_string(csr_data)
            if not csr:
                return False, 'INV_CSR'

            cert_id, cn, ser_no = self._check_cert2req(crt_file_name, csr)
            if cert_id:
                # All is fine, cert is verified to be issued
                # from the sent request and is OK to be send to node
                try:
                    ca_cert = ""
                    if self.config.security.use_org:
                        # Return SubCA+CA
                        subca_cert_file = p.join(p.dirname(p.abspath(
                            self.config.security.ca)),
                            'org', cert_id + '.ca.crt')
                        ca_cert = '%s%s' % (
                            open(subca_cert_file).read(),
                            open(self.config.security.ca).read())
                    else:
                        # Return CA
                        ca_cert = open(self.config.security.ca).read()

                    # Write record in /nodes
                    node_cert_name = p.join(
                        p.dirname(p.abspath(self.config.security.ca)),
                        'nodes',
                        '%s.%s.crt' % (cert_id, cn))
                    open(node_cert_name, 'w').write(str(ser_no))
                    return True, (
                        open(crt_file_name).read() +
                        TOKEN_SEPARATOR +
                        ca_cert +
                        TOKEN_SEPARATOR +
                        open(self.config.security.server_cert).read())
                except:
                    raise
            else:
                # Issued CRT already exists,
                # and doesn't match current csr
                return False, 'ERR_CRT_EXISTS'
        except Exception, ex:
            LOGA.exception(ex)
            return False, 'UNKNOWN'
        finally:
            # clear locally stored crt files
            if p.exists(crt_file_name):
                os.unlink(crt_file_name)
            del csr

    def register_session(self, session_id):
        self.managed_sessions[session_id] = True

    def unregister_session(self, session_id):
        try:
            self.managed_sessions.pop(session_id)
        except:
            pass

    def verify_node_request(self, node, request):
        base_path = p.join(p.dirname(
            p.abspath(self.config.security.ca)))
        # Check if node is already requested or signed

        # if node in self.ccont.list_all_approved():
        # cert already issued
        #    return self._build_cert_response(node, request, crt_file_name)
        # Saving CSR
        csr = None
        try:
            csr = m.X509.load_request_string(str(request))
            subj = csr.get_subject()
            CN = subj.CN
            OU = subj.OU or 'no--org'
            csr_file_name = p.join(base_path, 'reqs',
                                   '.'.join([OU, node, 'csr']))
            crt_file_name = p.join(base_path,
                                   'issued',
                                   '.'.join([OU, node, 'crt']))
            if CN != node:
                return False, "ERR_CN_FAIL"
            if not is_valid_host(CN):
                return False, "ERR_NAME_FORBD"
            if p.exists(crt_file_name):
                return self._build_cert_response(node, request, crt_file_name)
            csr.save(csr_file_name)
            LOGA.info("Saved CSR file: %s" % csr_file_name)
        except Exception, ex:
            LOGA.exception(ex)
            return False, 'INV_CSR'
        finally:
            del csr

        if self.ccont.can_approve(node):
            kwargs = {}
            if self.config.security.trust_verify:
                kwargs['auto'] = True
            messages, crt_file = self.ccont.sign_node(node, **kwargs)
            for _, data in messages:
                LOGA.info(data)
            if crt_file:
                return self._build_cert_response(node, request, crt_file)
            else:
                return False, 'APPR_FAIL'
        else:
            if p.exists(csr_file_name):
                # Not issued yet
                return False, 'PENDING'
            elif not request:
                return False, 'SEND_CSR'

    def configure(self, overwrite=False, **kwargs):
        pass

    def loop(self):
        ioloop.IOLoop.instance().start()

    def prepare(self):
        # Run router devices
        self.router.start()

        def requests_queue():
            # Routes requests from master listener(pubid:5559) to workers
            router = self.context.socket(zmq.ROUTER)
            router.bind(self.buses.requests.publish)
            worker_proxy = self.context.socket(zmq.DEALER)
            worker_proxy.bind(self.buses.requests.consume)
            poller = zmq.Poller()
            poller.register(router, zmq.POLLIN)
            poller.register(worker_proxy, zmq.POLLIN)

            while not self.running.is_set():
                try:
                    socks = dict(poller.poll(500))
                    if router in socks:
                        frames = router.recv_multipart()
                        worker_proxy.send_multipart(frames)
                    if worker_proxy in socks:
                        frames = worker_proxy.recv_multipart()
                        router.send_multipart(frames)
                except zmq.ZMQError, err:
                    if self.context.closed or \
                            getattr(err, 'errno', 0) == zmq.ETERM or \
                            getattr(err, 'errno', 0) == zmq.ENOTSOCK:
                        # System interrupt
                        break
                    else:
                        raise err
                except KeyboardInterrupt:
                    break
            router.close()
            worker_proxy.close()
            LOGR.info("Exited requests queue")

        def logger_queue():
            # Logger proxy
            log_proxy = self.context.socket(zmq.DEALER)
            log_proxy.bind(self.buses.logger.publish)
            log_proxy_fwd = self.context.socket(zmq.DEALER)
            log_proxy_fwd.bind(self.buses.logger.consume)
            # Logger PUB forwarder
            log_pub_fwd = self.context.socket(zmq.PUB)
            log_pub_fwd.bind(self.buses.logger_fwd.publish)
            LOGL.info("Logger publishing at %s" %
                      self.buses.logger_fwd.publish)
            while not self.running.is_set():
                try:
                    if not log_proxy.poll(500):
                        continue
                    frames = log_proxy.recv()
                    log_proxy_fwd.send(frames)
                    log_pub_fwd.send(frames)
                    # zmq.device(zmq.FORWARDER, log_proxy, log_proxy_fwd)
                except zmq.ZMQError, err:
                    if self.context.closed or \
                            getattr(err, 'errno', 0) == zmq.ETERM or \
                            getattr(err, 'errno', 0) == zmq.ENOTSOCK or \
                            getattr(err, 'errno', 0) == zmq.ENOTSUP:
                        # System interrupt
                        break
                    LOGR.exception(err)
                    continue
                except KeyboardInterrupt:
                    break
                except Exception, ex:
                    LOGR.exception(ex)
                    continue

            log_proxy.close()
            log_proxy_fwd.close()
            log_pub_fwd.close(0)
            LOGR.info("Exited logger queue")

        def scheduler_queue():
            # Listens to scheduler queue and transmits to ...
            sched_proxy = self.context.socket(zmq.DEALER)
            sched_proxy.bind(self.buses.scheduler.publish)
            sched_proxy_fwd = self.context.socket(zmq.DEALER)
            sched_proxy_fwd.bind(self.buses.scheduler.consume)
            while not self.running.is_set():
                try:
                    zmq.device(zmq.QUEUE, sched_proxy, sched_proxy_fwd)
                except zmq.ZMQError, err:
                    if self.context.closed or \
                            getattr(err, 'errno', 0) == zmq.ETERM or \
                            getattr(err, 'errno', 0) == zmq.ENOTSOCK or \
                            getattr(err, 'errno', 0) == zmq.ENOTSUP:
                        # System interrupt
                        break
                    LOGR.exception(err)
                    continue
                except KeyboardInterrupt:
                    break

            sched_proxy.close()
            sched_proxy_fwd.close()
            LOGR.info("Exited scheduler queue")

        def user_input_queue():
            uinput_service = self.context.socket(zmq.ROUTER)
            uinput_service.bind(self.buses['user_input'].publish)
            uinput_proxy = self.context.socket(zmq.ROUTER)
            uinput_proxy.bind(self.buses['user_input'].consume)
            while not self.running.is_set():
                try:
                    frames = uinput_service.recv_multipart()
                    frames.pop(0)
                    uinput_proxy.send_multipart(frames)
                except zmq.ZMQError, err:
                    if self.context.closed or \
                            getattr(err, 'errno', 0) == zmq.ETERM or \
                            getattr(err, 'errno', 0) == zmq.ENOTSOCK:
                        break
                    else:
                        raise err
                except KeyboardInterrupt:
                    break

            uinput_service.close()
            uinput_proxy.close()
            LOGR.info("Exited user_input queue")

        Thread(target=requests_queue).start()
        self.bindings['requests'] = True
        self.bindings['replies'] = True

        Thread(target=logger_queue).start()
        self.bindings['logger'] = True

        self.bindings['in_messages'] = True
        self.bindings['out_messages'] = True

        Thread(target=scheduler_queue).start()
        self.bindings['scheduler'] = True

        Thread(target=user_input_queue).start()
        self.bindings["user_input"] = True

        Thread(target=self.pubsub_queue).start()

        if self.proxies:
            Thread(target=self.proxy_replicator).start()
            self.bindings["replicator"] = True

    def heartbeat(self, msg):
        if msg.control == 'QUIT':
            LOGPUB.info("QUIT: Node %s dropped from %s" % (
                msg.hdr.peer, msg.hdr.org))
            if msg.hdr.org in self.tenants:
                self.tenants[msg.hdr.org].pop(msg.hdr.peer)
        elif msg.hdr.org not in self.tenants:
            LOGPUB.warn("Unrecognized node: %s" % msg)
        else:
            if self.config.security.use_org:
                LOGPUB.info("HB from %s@%s" % (msg.hdr.peer, msg.hdr.org))
            else:
                LOGPUB.info("HB from %s" % msg.hdr.peer)

            if self.tenants[msg.hdr.org].push(msg.hdr.peer):
                # New node
                LOGPUB.info("Node %s attached to %s" % (msg.hdr.peer,
                                                        msg.hdr.org))
                return True

    def pubsub_queue(self):
        # Intercepts PUB-SUB messages from Publisher
        # and forwards to Master PUB socket(5551)

        xsub_listener = self.context.socket(zmq.XSUB)
        xsub_listener.bind(self.buses.publisher.publish)
        xpub_listener = self.context.socket(zmq.XPUB)
        xpub_listener.bind(self.buses.publisher.consume)

        heartbeat = self.context.socket(zmq.DEALER)
        heartbeat.setsockopt(zmq.IDENTITY, HEARTBEAT)
        heartbeat.connect(self.buses.in_messages.consume)

        node_reply_queue = self.publish_queue('out_messages')

        poller = zmq.Poller()
        poller.register(xpub_listener, zmq.POLLIN)
        poller.register(xsub_listener, zmq.POLLIN)
        poller.register(heartbeat, zmq.POLLIN)

        pub_proxy = None

        if self.proxies:
            pub_proxy = self.context.socket(zmq.DEALER)
            pub_proxy.bind(self.endpoints['pub_fwd'])
            poller.register(pub_proxy, zmq.POLLIN)

        # Subscribe upstream for all feeds
        xsub_listener.send('\x01')

        def _ping_nodes(*args):
            try:
                for name, tenant in self.tenants.items():
                    # Set 1 refresh time back to avoid missing active nodes
                    self.tenants[name].refresh(adjust=-self.heartbeat_timeout)
                    xpub_listener.send_multipart(
                        [tenant.id, HB()._])
            except zmq.ZMQError, err:
                if self.context.closed or \
                        getattr(err, 'errno', 0) == zmq.ETERM or \
                        getattr(err, 'errno', 0) == zmq.ENOTSOCK:
                    return
            except Exception, ex:
                LOGPUB.error(ex)

        def translate(org_name):
            # Translate org_name to org_uid
            try:
                org_uid = self.tenants[org_name].id
                return org_uid
            except:
                LOGPUB.error("Problem dispatching to tenant %s. "
                             "Restart of nodes might be needed" %
                             org_name)

        def process(msg):
            msg.hdr.clear()
            if self.crypter:
                return self.crypter.encrypt(msg._)
            else:
                return msg._

        timer = Timer(self.heartbeat_timeout, _ping_nodes)
        timer.start()
        LOGPUB.info("Heartbeat at %s sec" % self.heartbeat_timeout)

        while not self.running.is_set():
            try:
                socks = dict(poller.poll(1000))
                if not socks:
                    continue
                if zmq.POLLERR in socks.values():
                    LOGPUB.error("Socket error in PUBSUB")

                if xpub_listener in socks:
                    packet = xpub_listener.recv_multipart()
                    action = packet[0][0]
                    target = packet[0][1:]
                    if action == b'\x01' and target:

                        if target not in self.tenants.values():
                            # Send welcome message
                            xpub_listener.send_multipart([target,
                                                          Welcome()._])
                        else:
                            tenant = [(t_key, t_val) for t_key, t_val in
                                      self.tenants.items()
                                      if t_val == target][0][0]
                            LOGPUB.info(
                                'Started publishing on %s' % tenant)
                            xpub_listener.send_multipart(
                                [target, HB()._])
                    elif action == b'\x00':
                        # Node de-registered
                        LOGPUB.debug('Stopped publishing to %s' %
                                     target)
                        if target in self.tenants.values():
                            # Active node dropped,
                            # force tenant nodes to reload
                            for tenant in self.tenants.values():
                                if tenant == target:
                                    LOGPUB.info("Node dropped from %s" %
                                                tenant.name)
                                    # Refresh HeartBeat
                                    self.tenants[tenant.name].refresh()
                                    xpub_listener.send_multipart(
                                        [target, HB()._])
                                    break
                if xsub_listener in socks:
                    packed = xsub_listener.recv()
                    LOGPUB.debug("XSUB packet %s" % packed)

                    msg = M.build(packed)
                    if isinstance(msg, JobTarget):
                        org_name = msg.hdr.org or DEFAULT_ORG
                        org_uid = translate(org_name)
                        if org_uid:
                            xpub_listener.send_multipart(
                                [org_uid, Crypto(process(msg))._])
                            if pub_proxy:
                                # Forward to other masters
                                pub_proxy.send(
                                    Fwd(org_name, packed)._)
                                LOGPUB.debug(
                                    "PUB FWD %s" % ([org_name] + packed))

                    elif isinstance(msg, Fwd):
                        # Received forwarded packet?
                        org_name = msg.hdr.org or DEFAULT_ORG
                        org_uid = translate(org_name)
                        if org_uid:
                            xpub_listener.send_multipart(
                                [org_uid, Crypto(process(msg))._])

                if heartbeat in socks:
                    packed = heartbeat.recv()
                    req = M.build(packed)

                    if not req:
                        LOGPUB.warn("Invalid HB request: %s" % req)
                        continue

                    if isinstance(req, (HBR, Ident, Quit)):
                        try:
                            if self.heartbeat(req):
                                msg = Init(self.tenants[req.hdr.org].id,
                                           req.hdr.org,
                                           self.crypter.key,
                                           self.crypter.iv)
                                msg.header(ident=req.hdr.ident)
                                node_reply_queue.send(msg._)
                        except Exception, ex:
                            LOGR.exception(ex)
                    elif pub_proxy:
                        # Also notify other masters
                        pub_proxy.send(Fwd(req.org, 'HB')._)
                if pub_proxy in socks:
                    packed = pub_proxy.recv()
                    msg = M.build(packed)
                    if not isinstance(msg, Fwd):
                        continue
                    # Received forwarded packet?
                    org_name = msg.dest.org or DEFAULT_ORG
                    org_uid = translate(org_name)
                    if org_uid:
                        xpub_listener.send_multipart(
                            [org_uid, Crypto(process(msg))._])

            except zmq.ZMQError, err:
                if self.context.closed or \
                        getattr(err, 'errno', 0) == zmq.ETERM or \
                        getattr(err, 'errno', 0) == zmq.ENOTSOCK or \
                        getattr(err, 'errno', 0) == zmq.ENOTSUP:
                    # System interrupt
                    break
                LOGPUB.exception(err)
                continue
            except KeyboardInterrupt:
                break

        timer.stop()
        if pub_proxy:
            pub_proxy.close(0)
        node_reply_queue.close()
        xsub_listener.close()
        xpub_listener.close()
        heartbeat.close()
        LOGPUB.info("Exited PUBSUB thread")

    def proxy_replicator(self):
        # self -> other masters
        poller = zmq.Poller()

        # proxy publisher
        pub_proxy = self.context.socket(zmq.XPUB)
        pub_proxy.bind(self.endpoints['replicator'])
        poller.register(pub_proxy, zmq.POLLIN)

        # proxy receiver
        pub_proxy_sub = self.context.socket(zmq.SUB)
        verbs = ['SYNC', 'HB', 'PUB', 'IN', 'OUT']
        for verb in verbs:
            pub_proxy_sub.setsockopt(zmq.SUBSCRIBE, verb)
        pub_proxy_sub.setsockopt(zmq.SUBSCRIBE, self.host)

        # proxy <-> router <-> proxy
        router_proxy = self.context.socket(zmq.DEALER)
        router_proxy.connect(self.endpoints['router_fwd'])
        poller.register(router_proxy, zmq.POLLIN)

        # proxy <-> pubsub <-> proxy
        pubsub_proxy = self.context.socket(zmq.DEALER)
        pubsub_proxy.connect(self.endpoints['pub_fwd'])
        poller.register(pubsub_proxy, zmq.POLLIN)

        for host, proxy in self.proxies.items():
            try:
                pub_proxy_sub.connect('tcp://%s' % proxy)
                LOGR.info("Connected to proxy: %s" % proxy)
            except Exception, ex:
                LOGR.error(ex)
        poller.register(pub_proxy_sub, zmq.POLLIN)

        # Send nodes
        def sync():
            for tenant in self.tenants.values():
                for node in tenant.nodes:
                    pub_proxy.send(HB()._)
        sync()
        pub_proxy.send('SYNC')

        while not self.running.is_set():
            try:
                socks = dict(poller.poll(1000))
                if not socks:
                    continue
                if pub_proxy in socks:
                    flag = pub_proxy.recv()
                    _type = flag[0]
                    tag = flag[1:]
                    if tag not in verbs:
                        if _type == b'\x00':
                            # Disconnect
                            LOGR.info("Proxy %s disconnected" % tag)
                        if _type == b'\x01' and tag not in self.proxies:
                            LOGR.info("Reconnecting to proxy: %s" % tag)
                            try:
                                pub_proxy_sub.connect('tcp://%s' % proxy)
                                LOGR.info(
                                    "Connected to proxy: %s" % proxy)
                            except Exception, ex:
                                LOGR.error(ex)

                if pub_proxy_sub in socks:
                    packets = pub_proxy_sub.recv_multipart()
                    msg = Fwd.build(**packets)
                    if not msg:
                        LOGPUB.warning("Unknown fwd message: %s" % packets)
                        continue
                    target = msg.control
                    if target == 'SYNC':
                        sync()
                    elif target == 'HB':
                        # Heartbeat
                        req = HB.build()
                        if not req:
                            LOGR.warn("Invalid HB request: %s" % packets)
                        else:
                            self.heartbeat(req)
                    elif target == 'PUB':
                        # Publish job
                        packets.insert(1, 'FWD')
                        # ------------
                        pubsub_proxy.send_multipart(packets)
                    elif target in ['IN', 'OUT']:
                        router_proxy.send_multipart([target] + packets)

                if router_proxy in socks:
                    # ------------
                    fwd_packets = router_proxy.recv_multipart()
                    LOGR.debug("fwd packets: %s" % fwd_packets)
                    pub_proxy.send_multipart(fwd_packets)

                if pubsub_proxy in socks:
                    # ------------
                    pubsub_packets = pubsub_proxy.recv_multipart()
                    LOGR.debug("pubsub fwd packets: %s" % pubsub_packets)
                    pub_proxy.send_multipart(pubsub_packets)

            except zmq.ZMQError, err:
                if self.context.closed or \
                        getattr(err, 'errno', 0) == zmq.ETERM or \
                        getattr(err, 'errno', 0) == zmq.ENOTSOCK or \
                        getattr(err, 'errno', 0) == zmq.ENOTSUP:
                    # System interrupt
                    break
                LOGR.exception(err)
                continue
            except Exception, ex:
                LOGR.error(ex)

        pub_proxy.close()
        pub_proxy_sub.close()
        router_proxy.close()
        pubsub_proxy.close()
        LOGR.info("Exited replicator thread")

    def _validate(self, endp_type, ident):
        if endp_type not in self.buses:
            raise ValueError("Type %s not in allowed types %s" % (
                endp_type, self.buses))
        # if ident and len(ident) > 32:
        #    raise ValueError(
        #        "Socket identity cannot be larger than 32 symbols")

    def create_poller(self, *sockets):
        return PollerWrapper(*sockets)

    def consume_queue(self, endp_type, ident=None, **kwargs):
        self._validate(endp_type, ident)
        return self._connect(endp_type, self.buses[endp_type].consume, ident)

    def publish_queue(self, endp_type, ident=None, **kwargs):
        self._validate(endp_type, ident)
        if self.bindings.get(endp_type) is None:
            LOGR.warn("There is no bound socket here [%s], %s" % (
                endp_type, self.bindings.keys()))
        return self._connect(endp_type, self.buses[endp_type].publish, ident)

    def _connect(self, endp_type, endpoint, ident):
        sock = self.context.socket(zmq.DEALER)
        if ident:
            sock.setsockopt(zmq.IDENTITY, ident)
        sock.connect(endpoint)
        _sock = SockWrapper(endpoint, sock)
        self._sockets.append(_sock)
        return _sock

    def create_fanout(self, endpoint, *args, **kwargs):
        sock = self.context.socket(zmq.PUB)
        # Connect here, all binds are defined in router
        sock.connect(getattr(self.buses, endpoint).publish)
        _sock = SockWrapper(endpoint, sock)
        self._sockets.append(_sock)
        return _sock

    def subscribe_fanout(self, endpoint, sub_pattern=None, *args, **kwargs):
        sock = self.context.socket(zmq.SUB)
        sock.setsockopt(zmq.SUBSCRIBE, sub_pattern or '')
        sock.connect(getattr(self.buses, endpoint).consume)
        _sock = SockWrapper(endpoint, sock)
        self._sockets.append(_sock)
        return _sock

    def terminate(self):
        ioloop.IOLoop.instance().stop()
        for sock in self._sockets:
            LOGR.debug("Closing %s", sock.endpoint)
            sock._sock.close()
        self.running.set()
        self.router.close()
        self.context.term()


class Router(Thread):

    """
        Receives and routes data from nodes to clients and back
    """

    def __init__(self, config, context, buses, endpoints, event, proxies):
        super(Router, self).__init__()
        self.config = config
        self.context = context
        self.buses = buses
        self.endpoints = endpoints
        self.running = event
        self.proxies = proxies
        self.ssl_worker_uri = 'inproc://ssl-worker'

    def router_worker(self):
        # Collects all IN_MESSAGES and routes them
        # to the specified recipient
        try:
            router = self.context.socket(zmq.ROUTER)
            router.bind(self.buses.in_messages.consume)
        except zmq.ZMQError, zerr:
            if zerr.errno == 2:
                # Socket dir is missing
                LOGR.error("Socket uri is missing: %s" %
                           self.buses.in_messages.consume)
            return

        reply_router = self.context.socket(zmq.DEALER)
        reply_router.bind(self.buses.out_messages.publish)

        ssl_worker = self.context.socket(zmq.DEALER)
        ssl_worker.bind(self.ssl_worker_uri)

        poller = zmq.Poller()
        poller.register(reply_router, zmq.POLLIN)
        poller.register(ssl_worker, zmq.POLLIN)

        router_proxy = None
        if self.proxies:
            router_proxy = self.context.socket(zmq.DEALER)
            router_proxy.bind(self.endpoints['router_fwd'])
            poller.register(router_proxy, zmq.POLLIN)

        def do_ssl_msg(msg):

            if not msg.hdr.peer and msg.hdr.dest != ADMIN_TOWER:
                # Anonymous accessing data feed
                LOGR.error('NOT AUTHORIZED: %s : %r' % (msg.hdr.peer, msg))
                return

            if not self.config.security.use_org:
                msg.hdr.org = DEFAULT_ORG

            LOGR.debug(
                "Routing to: %r" % msg.route())
            router.send_multipart(msg.route())
            if router_proxy and msg.hdr.dest not in \
                    ZmqTransport.managed_sessions:
                router_proxy.send_multipart(
                    ["IN", msg.hdr.dest, msg._])

        socks = {}
        while not self.running.is_set():
            try:
                socks = dict(poller.poll(100))
            except zmq.ZMQError, zerr:
                if zerr.errno == zmq.ETERM or zerr.errno == zmq.ENOTSUP \
                        or zerr.errno == zmq.ENOTSOCK:
                    break
                continue
            try:
                for sock in socks:
                    # INCOMING #############
                    if sock == ssl_worker:

                        data = ssl_worker.recv()
                        msgs = M.parse(data)
                        for msg in msgs:
                            LOGR.debug("Msg recv: %r, %r" % (msg, msg.hdr))
                            do_ssl_msg(msg)

                    # REPLIES #############
                    if sock == reply_router:
                        packed = reply_router.recv()
                        msg = M.parse(packed)[0]
                        LOGR.debug("OUT-MSG reply: %r" % msg._)
                        ssl_worker.send(msg._)

                        if router_proxy:
                            if msg.hdr.dest not in [ADMIN_TOWER]:
                                router_proxy.send_multipart(
                                    ["OUT"] + msg.forward())

                    # ROUTER PROXY #############
                    if router_proxy and router_proxy == sock:
                        fwd_packet = router_proxy.recv_multipart()
                        LOGR.debug("FWD %s" % fwd_packet)
                        direction = fwd_packet.pop(0)
                        if direction == "IN":
                            sess_id = fwd_packet[0]
                            if (sess_id == HEARTBEAT and
                                fwd_packet[4] != 'IDENT') or \
                                    sess_id in \
                                    ZmqTransport.managed_sessions:
                                router.send_multipart(fwd_packet)
                        elif direction == "OUT":
                            fwd_msg = Fwd.build(**fwd_packet)
                            if fwd_msg:
                                sid = fwd_msg.data[0]
                                if sid not in \
                                        ZmqTransport.managed_sessions:
                                    ssl_worker.send_multipart(fwd_packet)

            except zmq.ZMQError, zerr:
                if zerr.errno == zmq.ETERM or zerr.errno == zmq.ENOTSUP \
                        or zerr.errno == zmq.ENOTSOCK:
                    break
        router.close()
        reply_router.close()
        ssl_worker.close()
        if router_proxy:
            router_proxy.close(0)

        LOGR.info("Exited router worker")

    def run(self):
        """ Run response processing thread """
        # Socket to receive replies
        self.repl_sock = self.context.socket(zmq.ROUTER)
        self.repl_sock.bind(self.endpoints['node_reply'])
        threads = []

        t = Thread(target=self.router_worker)
        threads.append(t)
        t.start()

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
            verify_func=verify_loc,
            cert_password=self.config.security.cert_pass)

        def master():
            # Runs the SSL Thread
            while not self.running.is_set():
                try:
                    self.master_repl.start()  # Start TLS ZMQ server socket
                except zmq.ZMQError, zerr:
                    if zerr.errno == zmq.ETERM or zerr.errno == zmq.ENOTSUP \
                            or zerr.errno == zmq.ENOTSOCK:
                        # System interrupt
                        break
                except KeyboardInterrupt:
                    break
                except Exception, ex:
                    LOGR.exception(ex)

        t = Thread(target=master)
        t.start()
        threads.append(t)

        for thread in threads:
            thread.join()

        self.master_repl.terminate()
        self.repl_sock.close()
        LOGR.info("Exited router device threads")

    def close(self, *args):
        self.running.set()
        LOGR.info("Stopping router")
        # self.repl_sock.close()
        # self.master_repl.terminate()
        LOGR.info("Stopped router")
