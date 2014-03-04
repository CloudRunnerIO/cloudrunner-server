import fcntl
import json
import logging
import M2Crypto as m
import os
from os import path as p
import signal
from threading import Event
from threading import Thread
import time
import zmq
from zmq.eventloop import ioloop

from .tlszmq import TLSZmqServerSocket
from .tlszmq import TLSServerCrypt
from cloudrunner.core.message import (ClientReq, ClientRep, RerouteReq,
                                      HEARTBEAT, ADMIN_TOWER, TOKEN_SEPARATOR,
                                      HeartBeatReq, DEFAULT_ORG,  StatusCodes,
                                      is_valid_host)
from cloudrunner.plugins.transport.zmq_transport import (SockWrapper,
                                                         PollerWrapper)
from cloudrunner.util.shell import Timer
from cloudrunner_server.plugins.transport.base import (ServerTransportBackend,
                                                       Tenant)
from cloudrunner_server.master.functions import CertController

LOGR = logging.getLogger('ZMQ ROUTER')
LOGP = logging.getLogger('ZMQ PUB FWD')


class Pipe(object):

    def __init__(self, publish, consume):
        self.publish = publish
        self.consume = consume


class DictWrapper(dict):

    def __getattr__(self, item):
        if item in self.keys():
            return self[item]
        else:
            raise IndexError(item)

    def __setattr__(self, item, value):
        self[item] = value


class ZmqTransport(ServerTransportBackend):

    proto = "zmq+ssl"

    def __init__(self, config):
        self.preprocessor = []
        self.context = zmq.Context()
        self.bindings = {}
        self.running = Event()
        self._sockets = []
        self.ccont = CertController(config)

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

        self.endpoints = {
            'logger':
            "inproc://logger-queue",
            'logger_fanout':
            config.logger_uri or (
                "ipc://%(sock_dir)s/logger.sock" % config),
            'node_reply':
            'tcp://%s' % config.master_repl,
            'publisher':
            "inproc://pub-proxy.sock",
        }

        self.config = config
        self.router = Router(self.config, self.context,
                             self.buses, self.endpoints, self.running)
        self.crypter = TLSServerCrypt(config.security.server_key,
                                      cert_password=config.security.cert_pass)
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
        fd = None

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
            LOGP.exception(ex)
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
                    return True, (open(crt_file_name).read() +
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
            LOGP.exception(ex)
            return False, 'UNKNOWN'
        finally:
            # clear locally stored crt files
            if p.exists(crt_file_name):
                os.unlink(crt_file_name)
            del csr

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
            LOGP.info("Saved CSR file: %s" % csr_file_name)
        except Exception, ex:
            LOGP.exception(ex)
            return False, 'INV_CSR'
        finally:
            del csr

        if self.ccont.can_approve(node):
            kwargs = {}
            if self.config.security.trust_verify:
                kwargs['auto'] = True
            messages, crt_file = self.ccont.sign_node(node, **kwargs)
            for _, data in messages:
                LOGP.info(data)
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
            while not self.running.is_set():
                try:
                    zmq.device(zmq.QUEUE, router, worker_proxy)
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

        def finished_jobs_queue():
            # Routes requests from job_done queue to user (on pubip:5559)
            job_done = self.context.socket(zmq.DEALER)
            job_done.bind(self.buses.finished_jobs.consume)
            worker_out_proxy = self.context.socket(zmq.DEALER)
            worker_out_proxy.bind(self.buses.finished_jobs.publish)

            while not self.running.is_set():
                try:
                    zmq.device(zmq.QUEUE, worker_out_proxy, job_done)
                except zmq.ZMQError, err:
                    if self.context.closed or \
                            getattr(err, 'errno', 0) == zmq.ETERM or \
                            getattr(err, 'errno', 0) == zmq.ENOTSOCK:
                        break
                    else:
                        raise err
                except KeyboardInterrupt:
                    break
            job_done.close()
            worker_out_proxy.close()
            LOGR.info("Exited requests queue")

        def logger_queue():
            # Listens to logger queue and transmits to ...
            log_xsub = self.context.socket(zmq.XSUB)
            log_xsub.bind(self.endpoints['logger'])
            log_xpub = self.context.socket(zmq.XPUB)
            log_xpub.bind(self.endpoints['logger_fanout'])
            while not self.running.is_set():
                try:
                    zmq.device(zmq.FORWARDER, log_xsub, log_xpub)
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

            log_xpub.close()
            log_xsub.close()
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

        Thread(target=finished_jobs_queue).start()
        self.bindings['finished_jobs'] = True

        Thread(target=logger_queue).start()

        self.bindings['in_messages'] = True
        self.bindings['out_messages'] = True

        Thread(target=scheduler_queue).start()
        self.bindings['scheduler'] = True

        Thread(target=user_input_queue).start()

        Thread(target=self.pubsub_queue).start()

        self.bindings["user_input"] = True

    def pubsub_queue(self):
        # Intercepts PUB-SUB messages from Publisher
        # and forwards to Master PUB socket(5551)

        xsub_listener = self.context.socket(zmq.XSUB)
        xsub_listener.bind(self.endpoints['publisher'])
        xpub_listener = self.context.socket(zmq.XPUB)
        xpub_listener.bind(self.master_pub_uri)

        heartbeat = self.context.socket(zmq.DEALER)
        heartbeat.setsockopt(zmq.IDENTITY, HEARTBEAT)
        heartbeat.connect(self.buses.in_messages.consume)

        node_reply_queue = self.publish_queue('out_messages')

        poller = zmq.Poller()
        poller.register(xpub_listener, zmq.POLLIN)
        poller.register(xsub_listener, zmq.POLLIN)
        poller.register(heartbeat, zmq.POLLIN)

        # Subscribe upstream for all feeds
        xsub_listener.send('\x01')

        def _ping_nodes(*args):
            try:
                for name, tenant in self.tenants.items():
                    # Set 1 refresh time back to avoid missing active nodes
                    self.tenants[name].refresh(adjust=-self.heartbeat_timeout)
                    xpub_listener.send_multipart(
                        [tenant.id, StatusCodes.HB])
            except:
                pass

        timer = Timer(self.heartbeat_timeout, _ping_nodes)
        timer.start()

        while not self.running.is_set():
            try:
                socks = dict(poller.poll(1000))
                if not socks:
                    continue
                if zmq.POLLERR in socks.values():
                    LOGP.error("Socket error in PUBSUB")

                if xpub_listener in socks:
                    packet = xpub_listener.recv_multipart()
                    action = packet[0][0]
                    target = packet[0][1:]
                    if action == b'\x01' and target:

                        if target not in self.tenants.values():
                            # Send welcome message
                            xpub_listener.send_multipart(
                                [target, StatusCodes.WELCOME])
                        else:
                            tenant = [(t_key, t_val) for t_key, t_val in
                                      self.tenants.items()
                                      if t_val == target][0][0]
                            LOGP.info('Started publishing on %s' % tenant)
                            xpub_listener.send_multipart(
                                [target, StatusCodes.HB])
                    elif action == b'\x00':
                        # Node de-registered
                        LOGP.debug('Stopped publishing to %s' %
                                   target)
                        if target in self.tenants.values():
                            # Active node dropped,
                            # force tenant nodes to reload
                            for tenant in self.tenants.values():
                                if tenant == target:
                                    LOGP.info("Node dropped from %s, " %
                                              tenant.name)
                                    # Refresh HeartBeat
                                    self.tenants[tenant.name].refresh()
                                    xpub_listener.send_multipart(
                                        [target, StatusCodes.HB])
                                    break
                if xsub_listener in socks:
                    packet = xsub_listener.recv_multipart()

                    if self.config.security.use_org:
                        org_name = packet.pop(0)
                    else:
                        packet.pop(0)  # remove
                        org_name = DEFAULT_ORG
                    # Translate org_name to org_uid
                    try:
                        org_uid = self.tenants[org_name].id
                    except:
                        LOGR.error("Problem dispatching to tenant %s. "
                                   "Restart of nodes might be needed" %
                                   org_name)
                    else:
                        if (self.crypter):
                            signed_packets = self.crypter.encrypt(*packet)
                            xpub_listener.send_multipart([org_uid,
                                                          signed_packets])
                        else:
                            xpub_listener.send_multipart([org_uid] + packet)
                if heartbeat in socks:
                    hb_msg = heartbeat.recv_multipart()
                    req = HeartBeatReq.build(*hb_msg)
                    if not req:
                        LOGR.info("Invalid HB request: %s" % hb_msg)
                        continue
                    if req.control == 'QUIT':
                        LOGR.info("Node %s dropped from %s" %
                                 (req.peer, req.org))
                        if req.org in self.tenants:
                            self.tenants[req.org].pop(req.peer)
                    elif req.org not in self.tenants:
                        LOGR.warn("Unrecognized node: %s" % hb_msg[1:3])
                    else:
                        if self.config.security.use_org:
                            LOGR.info("HB from %s@%s" % (req.peer, req.org))
                        else:
                            LOGR.info("HB from %s" % req.peer)
                        if self.tenants[req.org].push(req.peer):
                            # New node
                            LOGR.info("Node %s attached to %s" % (req.peer,
                                                                  req.org))
                        if req.control == 'IDENT':
                            node_reply_queue.send(req.ident, req.peer,
                                                  'SUB_LOC',
                                                  self.tenants[req.org].id,
                                                  self.tenants[req.org].name)

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

        timer.stop()
        node_reply_queue.close()
        xsub_listener.close()
        xpub_listener.close()
        heartbeat.close()
        LOGR.info("Exited PUBSUB thread")

    def _validate(self, endp_type, ident):
        if not endp_type in self.buses:
            raise ValueError("Type %s not in allowed types %s" % (
                endp_type, self.buses))
        # if ident and len(ident) > 32:
        #    raise ValueError(
        #        "Socket identity cannot be larger than 32 symbols")

    def create_poller(self, *sockets):
        return PollerWrapper(*sockets)

    def consume_queue(self, endp_type, ident=None, **kwargs):
        self._validate(endp_type, ident)
        sock = self.context.socket(zmq.DEALER)
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
        sock.connect(self.endpoints[endpoint])
        _sock = SockWrapper(endpoint, sock)
        self._sockets.append(_sock)
        return _sock

    def subscribe_fanout(self, endpoint, *args, **kwargs):
        sock = self.context.socket(zmq.SUB)
        sock.connect(self.endpoints[endpoint])
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

    def __init__(self, config, context, buses, endpoints, event):
        super(Router, self).__init__()
        self.config = config
        self.context = context
        self.buses = buses
        self.endpoints = endpoints
        self.running = event
        self.ssl_worker_uri = 'inproc://ssl-worker'

    def run(self):
        """ Run response processing thread """
        # Socket to receive replies
        self.repl_sock = self.context.socket(zmq.ROUTER)
        self.repl_sock.bind(self.endpoints['node_reply'])
        threads = []

        def router_worker():
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

            reply_router = self.context.socket(zmq.DEALER)
            reply_router.bind(self.buses.out_messages.publish)

            ssl_worker = self.context.socket(zmq.DEALER)
            ssl_worker.bind(self.ssl_worker_uri)

            poller = zmq.Poller()
            poller.register(reply_router, zmq.POLLIN)
            poller.register(ssl_worker, zmq.POLLIN)

            socks = {}
            while not self.running.is_set():
                try:
                    socks = dict(poller.poll(100))
                except zmq.ZMQError, zerr:
                    if zerr.errno == zmq.ETERM or zerr.errno == zmq.ENOTSUP \
                        or zerr.errno == zmq.ENOTSOCK:
                        break
                try:
                    if ssl_worker in socks:
                        packets = ssl_worker.recv_multipart()
                        req = ClientReq.build(*packets)
                        if not req:
                            if packets[0] == 'QUIT':
                                # Node exited
                                router.send_multipart(
                                    [HEARTBEAT] + packets * 2)
                            else:
                                LOGR.error(
                                    "Invalid request from Client %s" % packets)
                            continue
                        if req.dest == HEARTBEAT:
                            LOGR.debug('IN-MSG received: %s' % req)
                        else:
                            LOGR.info('IN-MSG received: %s' % req)

                        if not req.peer and req.dest != ADMIN_TOWER:
                            # Anonymous accessing data feed
                            LOGR.error('NOT AUTHORIZED: %s : %s' % (req.peer,
                                                                    req.dest))
                            continue

                        if not self.config.security.use_org:
                            req.org = DEFAULT_ORG

                        rer_packet = RerouteReq(req).pack()
                        if rer_packet and rer_packet[0] != HEARTBEAT:
                            LOGR.info('IN-MSG re-routed: %s' % rer_packet)

                        router.send_multipart(rer_packet)

                    elif reply_router in socks:
                        packets = reply_router.recv_multipart()
                        rep = ClientRep.build(*packets)
                        if not rep:
                            LOGR.error("Invalid reply received: %s" % packets)
                            continue
                        rep_packet = rep.pack()
                        LOGR.info("OUT-MSG reply: %s" % rep_packet[:2])
                        ssl_worker.send_multipart(rep_packet)
                except zmq.ZMQError, zerr:
                    if zerr.errno == zmq.ETERM or zerr.errno == zmq.ENOTSUP \
                        or zerr.errno == zmq.ENOTSOCK:
                        break
            router.close()
            reply_router.close()
            ssl_worker.close()
            LOGR.info("Exited router worker")

        t = Thread(target=router_worker)
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
            verify_loc=verify_loc,
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
