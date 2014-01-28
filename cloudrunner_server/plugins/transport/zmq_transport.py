import logging
from threading import Thread
import time
import zmq
from zmq.eventloop import ioloop

from cloudrunner.core.message import (ClientReq, ClientRep, RerouteReq,
                                      HEARTBEAT, ADMIN_TOWER, StatusCodes)
from cloudrunner.plugins.transport.zmq_transport import (SockWrapper,
                                                         PollerWrapper)
from cloudrunner_server.plugins.transport.base import ServerTransportBackend
from cloudrunner_server.plugins.transport.tlszmq import TLSZmqServerSocket
from cloudrunner_server.plugins.transport.tlszmq import TLSServerCrypt

LOGR = logging.getLogger('ZMQ ROUTER')
LOGP = logging.getLogger('ZMQ PUB FWD')
DEFAULT_ORG = "DEFAULT"


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
            'tcp://' + (config.listen_uri or '0.0.0.0:38123'),
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

        self.endpoints = {
            'session': "ipc://%(sock_dir)s/pub-mngmt.sock" % config,
            'logger': "inproc://logger-queue",
            'logger_fanout': config.logger_uri or (
            "ipc://%(sock_dir)s/logger.sock" % config),
            'node_reply': 'tcp://%s' % config.master_repl,
            'publisher': "inproc://pub-proxy.sock",
        }

        self.config = config
        self.router = Router(self.config, self.context,
                             self.buses, self.endpoints)
        self.crypter = TLSServerCrypt(config.security.server_key,
                                      cert_password=config.security.cert_pass)

    def prepare(self):
        # Run router devices

        self.router.start()

        def requests_queue():
            # Routes requests from master listener(pubid:38123) to workers
            router = self.context.socket(zmq.ROUTER)
            router.bind(self.buses.requests.publish)
            worker_proxy = self.context.socket(zmq.DEALER)
            worker_proxy.bind(self.buses.requests.consume)
            while True:
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

        def finished_jobs_queue():
            # Routes requests from job_done queue to user (on pubip:38123)
            job_done = self.context.socket(zmq.DEALER)
            job_done.bind(self.buses.finished_jobs.consume)
            worker_out_proxy = self.context.socket(zmq.DEALER)
            worker_out_proxy.bind(self.buses.finished_jobs.publish)

            # For use of monitoring proxy
            # mon_proxy = self.context.socket(zmq.PUB)
            # mon_proxy.bind(self.mon_proxy_uri)
            # LOGR.info("Monitor writing on %s" % self.mon_proxy_uri)
            while True:
                try:
                    zmq.device(zmq.QUEUE, worker_out_proxy, job_done)
                    # monitored_queue(worker_out_proxy, job_done, mon_proxy)
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
            # mon_proxy.close()

        def logger_queue():
            # Listens to loger queue and transmits to ...
            log_xsub = self.context.socket(zmq.XSUB)
            log_xsub.bind(self.endpoints['logger'])
            log_xpub = self.context.socket(zmq.XPUB)
            log_xpub.bind(self.endpoints['logger_fanout'])
            while True:
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

        def pubsub_queue():
            # Intercepts PUB-SUB messages from Publisher
            # and forwards to Master PUB socket(5551)
            xsub_listener = self.context.socket(zmq.XSUB)
            xsub_listener.bind(self.endpoints['publisher'])
            xpub_listener = self.context.socket(zmq.XPUB)
            xpub_listener.bind(self.master_pub_uri)

            poller = zmq.Poller()
            poller.register(xpub_listener, zmq.POLLIN)
            poller.register(xsub_listener, zmq.POLLIN)

            # Subscribe upstream for all feeds
            xsub_listener.send('\x01')
            tenants = {DEFAULT_ORG: Tenant(DEFAULT_ORG, "CloudRunner")}

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
                            LOGP.info('Node started listening to %s' % target)
                            if target not in tenants.values():
                                # Send welcome message
                                xpub_listener.send_multipart(
                                    [target, StatusCodes.WELCOME])
                        elif action == b'\x00':
                            # Node de-registered
                            LOGP.info('Node stopped listening to %s' %
                                      target)
                            if target in tenants.values():
                                # Active node dropped,
                                # force tenant nodes to reload
                                for tenant in tenants.values():
                                    if tenant == target:
                                        LOGP.info("Node dropped from %s, " %
                                                  tenant.name)
                                        break
                                    # xpub_listener.send_multipart(
                                    #    [target, StatusCodes.RELOAD])
                    if xsub_listener in socks:
                        packet = xsub_listener.recv_multipart()
                        # if packet[1] == 'HB':
                        #    xpub_listener.send_multipart(packet)
                        #    continue

                        if self.config.security.use_org:
                            org_name = packet.pop(0)
                        else:
                            packet.pop(0)  # remove
                            org_name = DEFAULT_ORG
                        # Translate org_name to org_uid
                        try:
                            org_uid = tenants[org_name].id
                        except:
                            LOGR.error("Problem dispatching to tenant %s. "
                                       "Restart of nodes might be needed" %
                                       org_name)
                            continue
                        if (self.crypter):
                            signed_packets = self.crypter.encrypt(*packet)
                            xpub_listener.send_multipart([org_uid,
                                                          signed_packets])
                        else:
                            xpub_listener.send_multipart([org_uid, packet])
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

        def user_input_queue():
            notification_service = self.context.socket(zmq.ROUTER)
            notification_service.bind(self.buses['user_input'].publish)
            notification_proxy = self.context.socket(zmq.ROUTER)
            notification_proxy.bind(self.buses['user_input'].consume)
            while True:
                try:
                    frames = notification_service.recv_multipart()
                    frames.pop(0)
                    notification_proxy.send_multipart(frames)
                except zmq.ZMQError, err:
                    if self.context.closed or \
                            getattr(err, 'errno', 0) == zmq.ETERM or \
                            getattr(err, 'errno', 0) == zmq.ENOTSOCK:
                        break
                    else:
                        raise err
                except KeyboardInterrupt:
                    break

            notification_service.close()
            notification_proxy.close()

        Thread(target=requests_queue).start()
        self.bindings['requests'] = True
        self.bindings['replies'] = True

        Thread(target=finished_jobs_queue).start()
        self.bindings['finished_jobs'] = True

        Thread(target=logger_queue).start()

        Thread(target=pubsub_queue).start()

        self.bindings['in_messages'] = True
        self.bindings['out_messages'] = True

        Thread(target=user_input_queue).start()
        self.bindings["user_input"] = True

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
        assert (self.bindings.get(endp_type) is not None), \
            "There is no bound socket here [%s], %s" % (
                endp_type, self.bindings.keys())
        return self._connect(endp_type, self.buses[endp_type].publish, ident)

    def _connect(self, endp_type, endpoint, ident):
        sock = self.context.socket(zmq.DEALER)
        if ident:
            sock.setsockopt(zmq.IDENTITY, ident)
        sock.connect(endpoint)
        return SockWrapper(endp_type, sock)

    def create_fanout(self, endpoint, *args, **kwargs):
        sock = self.context.socket(zmq.PUB)
        # Connect here, all binds are defined in router
        sock.connect(self.endpoints[endpoint])
        return SockWrapper(endpoint, sock)

    def subscribe_fanout(self, endpoint, *args, **kwargs):
        sock = self.context.socket(zmq.SUB)
        sock.connect(self.endpoints[endpoint])
        return SockWrapper(endpoint, sock)

    def terminate(self):
        self.context.destroy()
        self.router.close()


class Router(Thread):

    """
        Receives and routes data from nodes to clients and back
    """

    def __init__(self, config, context, buses, endpoints):
        super(Router, self).__init__()
        self.config = config
        self.context = context
        self.buses = buses
        self.endpoints = endpoints
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
            time.sleep(1)  # wait for 1 sec for sockets to come up
            while True:
                try:
                    socks = dict(poller.poll(100))
                    if not socks:
                        continue
                except zmq.ZMQError, zerr:
                    if zerr.errno == zmq.ETERM or zerr.errno == zmq.ENOTSUP \
                        or zerr.errno == zmq.ENOTSOCK:
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
                            LOGR.debug('IN-MSG received: %s' % req)
                        else:
                            LOGR.info('IN-MSG received: %s' % req)

                        if not req.peer and req.dest != ADMIN_TOWER:
                            # Anonymous accessing data feed
                            LOGR.error('NOT AUTHORIZED: %s : %s' % (req.peer,
                                                                    req.dest))
                            continue
                        LOGR.info('IN-MSG re-routed: %s' %
                                  RerouteReq(req).pack())

                        router.send_multipart(RerouteReq(req).pack())

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
            while True:
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

        ioloop.IOLoop.instance().start()

        self.master_repl.terminate()
        self.repl_sock.close()
        for thread in threads:
            thread.join()
        LOGR.info("Exited router device threads")

    def close(self, *args):
        LOGR.info("Stopping router")
        self.context.destroy()
        ioloop.IOLoop.instance().stop()
        # self.repl_sock.close()
        # self.master_repl.terminate()
        LOGR.info("Stopped router")


class Tenant(object):

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
            self.nodes.append(Tenant.Node(node))
        else:
            self.nodes[self.nodes.index(node)].created = time.time()
