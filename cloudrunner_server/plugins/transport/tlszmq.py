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
from StringIO import StringIO
import threading
import time
import zmq

LOGS = logging.getLogger('TLSZmq Server')
LOGC = logging.getLogger('TLSZmq Client')
SIGN_DIGEST = 'sha256'


class ConnectionException(Exception):
    pass


class ServerDisconnectedException(Exception):
    pass


class TLSZmqServerSocket(object):

    def __init__(self, socket, proc_socket_uri, cert, key, ca=None,
                 ssl_proto='sslv3', verify_loc=None, cert_password=None):
        """
        Creates a wrapper over Zmq socket, works only with zmq.ROUTER,
        zmq.DEALER, zmq.REQ sockets

        Arguments:

        socket      --  Zmq socket to wrap.

        proc_socket_uri  --  Zmq socket to send/recv packets for internal processing.

        cert        --  Server certificate - PEM-encoded file (e.g. server.crt).

        key         --  Server key - PEM-encoded file(e.g. server.key).

        ca          --  Server CA file for verification of client certificates.
                        PEM-encoded file(e.g. ca.crt).

        ssl_proto   --  SSL/TLS protocol to use. Valid values:
                            'sslv3' and 'tlsv1'

        verify_loc  --  Verify locations. Certificate file(s) to use to verify
                        client certificates. Used for multi-node setup.

        cert_password --    Certificate private key password

        """
        self.zmq_socket = socket
        self.proc_socket_uri = proc_socket_uri
        self.proto = ssl_proto
        self.cert = cert
        self.key = key
        self.ca = ca
        self.cert_pass = cert_password
        self.conns = {}
        self.verify_loc = verify_loc

    def start(self):

        proc_socket = self.zmq_socket.context.socket(zmq.DEALER)
        proc_socket.connect(self.proc_socket_uri)

        poller = zmq.Poller()
        poller.register(self.zmq_socket, zmq.POLLIN)
        poller.register(proc_socket, zmq.POLLIN)

        while True:
            try:
                (ident, enc_req, data) = (None, None, None)
                socks = dict(poller.poll())
                if self.zmq_socket in socks:
                    # Read from SSL socket
                    packets = self.zmq_socket.recv_multipart()
                    (ident, enc_req) = packets
                else:
                    # Read from workers
                    ident, data = proc_socket.recv_multipart()

                if enc_req == '-255':
                    # Remove me
                    if ident in self.conns:
                        LOGS.info('Removing %s from cache' % repr(ident))
                        (_, _conn, node_id, org_id) = self.conns.pop(ident)
                        proc_socket.send_multipart(['QUIT', node_id, org_id])
                        _conn.shutdown()
                        continue

                if ident not in self.conns:
                    self.conns[ident] = [
                        time.time(),
                        TLSZmqServer(ident, self.cert,
                                     self.key, self.ca,
                                     verify_loc=self.verify_loc,
                                     cert_password=self.cert_pass),
                        None, None]
                    LOGS.debug('Adding new conn %s' % ident)
                LOGS.debug(
                    "Total %s SSL Connection objects" % len(self.conns))
                tls = self.conns[ident][1]
                LOGS.debug("conns: %s" % self.conns.keys())

                if enc_req:
                    try:
                        tls.put_data(enc_req)
                        tls.update()
                    except ConnectionException, cex:
                        LOGS.error(cex)
                        continue

                if tls.can_recv():
                    plain_data = tls.recv()
                    client_id = ''
                    org_id = ''
                    if not self.conns[ident][2]:
                        try:
                            x509 = tls.ssl.get_peer_cert()
                            if x509:
                                subj = x509.get_subject()
                                client_id = subj.CN
                                org_id = subj.O
                                self.conns[ident][2] = client_id  # auth conn
                                self.conns[ident][3] = org_id  # auth conn
                        except Exception, ex:
                            self.conns[ident][2] = None  # not auth conn
                            self.conns[ident][3] = None  # not auth conn
                            LOGS.exception(ex)
                    else:
                        client_id = self.conns[ident][2]
                        org_id = self.conns[ident][3]

                    # assert client_id == tls.ssl.get_peer_cert().\
                    #   get_subject().CN

                    LOGS.debug("PLAIN: %s" % plain_data)
                    packets = plain_data.split('\x00')
                    for packet in packets:
                        if packet:
                            proc_socket.send_multipart(
                                [ident, client_id, org_id or '', packet])

                if data:
                    tls.send(data)
                    try:
                        flushed = tls.update()
                        is_auth = self.conns[ident][2]
                        if flushed and not is_auth:
                            LOGS.debug("Anon connection, dropping %s" % ident)
                            # Remove cached ssl obj for unauth reqs
                            (_t, conn, user, org) = self.conns.pop(ident)
                            conn.shutdown()
                    except ConnectionException, ex:
                        continue

                if tls.needs_write():
                    enc_rep = tls.get_data()
                    self.zmq_socket.send_multipart([ident, enc_rep])
            except zmq.ZMQError, zerr:
                if zerr.errno == zmq.ETERM or zerr.errno == zmq.ENOTSUP \
                    or zerr.errno == zmq.ENOTSOCK:
                    # System interrupt
                    break
            except KeyboardInterrupt:
                break
            except Exception, ex:
                LOGS.exception(ex)
                break

        self.terminate()
        LOGS.info("Server exited")

    def terminate(self):
        self.zmq_socket.close()
        for conn in self.conns.values():
            conn[1].shutdown()


class TLSZmqClientSocket(object):

    def __init__(self, context, ssl_socket_uri, socket_proc_uri, stopped_event,
                 cert=None, key=None, ssl_proto='sslv3', ca=None,
                 cert_password=None):
        """
        Creates a wrapper over Zmq socket, works only with zmq.ROUTER,
        zmq.DEALER, zmq.REQ sockets

        Arguments:

        context     --  ZMQ context

        ssl_socket_uri  --  URI to connect zmq socket to.

        socket_proc_uri --  Socket URI to communicate with caller

        stopped_event   --  Event to listen to

        cert        --  Server certificate - PEM-encoded file (e.g. client.crt).

        key         --  Server key - PEM-encoded file(e.g. client.key).

        ssl_proto   --  SSL/TLS protocol to use. Valid values:
                            'sslv3' and 'tlsv1'

        ca          --  CA file for server verification

        cert_password --    Certificate private key password

        """
        self.context = context
        self.ssl_socket_uri = ssl_socket_uri
        self.socket_proc_uri = socket_proc_uri
        self.proto = ssl_proto
        self.cert = cert
        self.key = key
        self.ca = ca
        self.cert_password = cert_password
        self.stopped = stopped_event

    def renew(self):
        LOGC.info("Renewing SSL client socket")
        if hasattr(self, 'tls'):
            self.tls.shutdown()

        if hasattr(self, 'zmq_socket'):
            self.poller.unregister(self.zmq_socket)
            self.zmq_socket.close()
            del self.zmq_socket

        self.tls = TLSZmqClient(self.proto, self.cert, self.key, ca=self.ca,
                                cert_password=self.cert_password)

        self.zmq_socket = self.context.socket(zmq.DEALER)
        self.zmq_socket.connect(self.ssl_socket_uri)
        self.poller.register(self.zmq_socket, zmq.POLLIN)

    def start(self):
        self.socket_proc = self.context.socket(zmq.ROUTER)
        self.socket_proc.bind(self.socket_proc_uri)

        self.poller = zmq.Poller()
        self.poller.register(self.socket_proc, zmq.POLLIN)
        self.renew()

        while not self.stopped.is_set():
            try:
                socks = dict(self.poller.poll(100))

                if self.socket_proc in socks:
                    data = self.socket_proc.recv_multipart()
                    LOGC.debug("Data to send %s" % data[:2])
                    data.pop(0)  # sender

                    self.tls.send(json.dumps(data))
                    self.tls.send('\x00')  # separator
                    self.tls.update()

                if self.tls.needs_write():
                    enc_msg = self.tls.get_data()
                    self.zmq_socket.send(enc_msg)

                if self.zmq_socket in socks:
                        enc_req = self.zmq_socket.recv()
                        self.tls.put_data(enc_req)
                        try:
                            self.tls.update()
                        except ConnectionException, ex:
                            # Possible SSL crash, try to self-heal
                            LOGC.warn(
                                "SSL transport failed, resending %s" % data)
                            self.renew()
                            self.tls.send(json.dumps(data))
                            self.tls.update()
                        except Exception, ex:
                            LOGC.exception(ex)
                            break

                if self.tls.can_recv():
                    resp_json = self.tls.recv()
                    try:
                        resp = json.loads(resp_json)
                        LOGC.debug("Data recvd %s" % resp[:2])
                        self.socket_proc.send_multipart(
                            [str(r) for r in resp])
                    except ValueError:
                        LOGC.error("Cannot decode message %s" % resp_json)

            except ConnectionException, connex:
                LOGC.error(connex)
                LOGC.warn("Rebuilding ssl connection")
                self.shutdown()
                raise
            except zmq.ZMQError, zerr:
                if zerr.errno == zmq.ETERM or zerr.errno == zmq.ENOTSUP \
                    or zerr.errno == zmq.ENOTSOCK:
                    # System interrupt
                    break
                LOGC.exception(zerr)
            except Exception, ex:
                raise

        self.poller.unregister(self.zmq_socket)
        self.poller.unregister(self.socket_proc)
        self.zmq_socket.send('-255')
        self.shutdown()
        LOGC.info("TLSZmqClient exited")

    def shutdown(self):
        LOGC.info('Closing TLSZmqClient')
        self.stopped.set()
        self.tls.shutdown()
        self.zmq_socket.close()
        self.socket_proc.close()
        LOGC.info('TLSZmqClient closed')


class _TLSZmq(object):

    _ctx = None

    def __init__(self, log, proto='sslv3', type='Server', identity=None,
                 cert=None, key=None, ca=None, verify_loc=None,
                 cert_password=None):
        """
        Creates a TLS/SSL wrapper for handling handshaking and encryption
        of messages over insecure sockets

        Arguments:

        proto       --  Protocol of the wrapper.
                        Valid values are: 'sslv3' or 'tlsv1'.
                        Required.

        type        --  Type of the instance - 'Server' or 'Client'

        identity    --  unique id of the wrapper. Max length is 32 chars, due to
                        limitation in OpenSSL. Needed for proper
                        packet handling. Required.

        cert        --  Certificate file name. Used on both
                        client and server side.
                        Mandatory for the server. Optional for the client.
                        Usually the client uses a signed certificate from the
                        server's CA.

        key         --  File name with PEM-encoded key of the client/server.
                        Mandatory with cert.

        ca          --  CA certificate file name. Not applicable for clients,
                        Mandatory with server that checks issues client certs.

        verify_loc  --  Verify locations. Certificate file(s) to use to verify
                        client certificates. Used for multi-node setup.

        cert_password --    Certificate private key password

        """
        self.DEPTH = 5
        self.BUF_LEN = 1024
        self.identity = identity
        self.LOG = log
        self.proto = proto
        assert self.proto in ('sslv3', 'tlsv1')
        self.cert = cert
        self.key = key
        assert (self.cert and self.key) or (not self.cert and not self.key)
        self.ca = ca
        self.verify_loc = verify_loc
        self.cert_password = cert_password
        assert (not self.ca) or (self.ca and self.cert and self.key)

        self.type = type
        if self.is_server:
            assert identity and len(self.identity) <= 32
        self._init_ctx()
        self._init_ssl()

    @property
    def is_server(self):
        return self.type == 'Server'

    @property
    def is_client(self):
        return self.type == 'Client'

    def set_verify_callback(self, verify_cb):
        """
        Sets a vertificate verification callback.
        Pass a function of the type:
            `def callback(X509cert, verify_depth, intermediate_status):`

        Where:
            X509Cert        --  a M2Crypto.X509.X509 object
            verify_depth    --  The depth of verification tree
            intermediate_status --  The status calculated so far.
                                    You can override this.
        """
        self.verify_cb = verify_cb

    def _verify_callback(self, ctx, _x509, errnum, depth, ok):
        if hasattr(self, 'verify_cb'):
            ok = self.verify_cb(x509, depth, ok)
            del x509
        return ok

    def _pass_callback(self, *args):
        return self.cert_password

    def _init_ctx(self):

        if _TLSZmq._ctx is None:
            self.LOG.debug('Creating SSL Context')
            # Init singleton SSL.Context
            _TLSZmq._ctx = m.SSL.Context(self.proto)

            if self.cert:
                try:
                    _TLSZmq._ctx.load_cert(self.cert, keyfile=self.key,
                                           callback=self._pass_callback)
                except m.SSL.SSLError, ex:
                    self.LOG.exception(ex)
                    self.LOG.error("Cannot load certificates:\n%s\n%s" %
                                   (self.cert, self.key))
        self.ctx = _TLSZmq._ctx

        self.ctx.set_options(m.SSL.op_no_sslv2)
        if self.is_server and self.ca:
            verify_flags = m.SSL.verify_peer
            verify_flags = verify_flags  # | m.SSL.verify_client_once
            self.ctx.set_verify(
                verify_flags, self.DEPTH, self._verify_callback)
            self.ctx.set_client_CA_list_from_file(self.ca)
            if self.verify_loc:
                if isinstance(self.verify_loc, basestring):
                    self.LOG.debug("Loading verification CA from %s" %
                                   self.verify_loc)
                    self.ctx.load_verify_locations(self.verify_loc)
                else:
                    for loc in self.verify_loc:
                        self.LOG.debug("Loading verification CA from %s" % loc)
                        self.ctx.load_verify_locations(loc)
        elif self.is_client:
            if self.ca:
                verify_flags = m.SSL.verify_peer
                self.ctx.set_allow_unknown_ca(0)
                self.ctx.load_verify_locations(self.ca)
                self.ctx.set_verify(
                    verify_flags, self.DEPTH, self._verify_callback)
            elif self.cert:
                if not hasattr(_TLSZmq, '_ca_warn'):
                    self.LOG.warn("Client certificate is used, but no CA cert "
                                  "is passed. The server will not be "
                                  "verified upon request")
                    _TLSZmq._ca_warn = 1  # show only once

    def _init_ssl(self):
        self.rbio = m.BIO.MemoryBuffer()
        self.wbio = m.BIO.MemoryBuffer()

        self.ssl = m.SSL.Connection(self.ctx, sock=None)
        self.ssl.set_bio(self.rbio, self.wbio)

        self.app_to_ssl = StringIO()
        self.ssl_to_zmq = StringIO()
        self.zmq_to_ssl = StringIO()
        self.ssl_to_app = StringIO()

        if self.is_server:
            if self.ca:
                self.ssl.set_client_CA_list_from_context()
            self.ctx.set_session_id_ctx(self.identity)
            self.ssl.set_session_id_ctx(self.identity)
            self.ssl.set_accept_state()
        else:
            self.ssl.set_connect_state()

    def update(self):
        sent = False
        if self.zmq_to_ssl.len:
            wrc = self.rbio.write(self.flush(self.zmq_to_ssl))
            self.LOG.debug('%s written to BIO' % (wrc))
        if self.app_to_ssl.len:
            rc = self.ssl.write(self.app_to_ssl.getvalue())
            if not self.continue_ssl(rc):
                raise Exception('SSL Error')
            if rc == self.app_to_ssl.len:
                self.app_to_ssl.truncate(0)
                sent = True
            self.LOG.debug("%s written to SSL" % (rc))

        self.net_read()
        self.net_write()
        return sent

    def continue_ssl(self, rc):
        err = self.ssl.ssl_get_error(rc)
        if err in (2, 1):
            # 1: SSL Error, possible cert issue
            # 2: SSL_ERROR_WANT_READ
            return True
        if err:
            self.LOG.error("SSL Error: [%s] %s" % (err,
                          (m.m2.err_reason_error_string(err))))
            return False
        return True

    def net_read(self):
        while True:
            try:
                rc = self.ssl.read(self.BUF_LEN)
            except m.SSL.SSLError, ex:
                # break
                if self.is_client:
                    raise ConnectionException(ex.message)
                self.LOG.error("SSL ERROR: %s" % str(ex))
                break
            if rc is None:
                break
            self.ssl_to_app.write(rc)

    def net_write(self):
        while True:
            try:
                read = self.wbio.read()
            except (m.SSL.SSLError, m.BIO.BIOError), ex:
                self.LOG.exception(ex)
                continue
            if read is None:
                break
            self.ssl_to_zmq.write(read)
        if self.ssl_to_zmq.len:
            self.LOG.debug("%s read from BIO" % (self.ssl_to_zmq.len))

    def can_recv(self):
        return self.ssl_to_app.len

    def needs_write(self):
        return self.ssl_to_zmq.len

    def recv(self):
        return self.flush(self.ssl_to_app)

    def get_data(self):
        return self.flush(self.ssl_to_zmq)

    def put_data(self, data):
        self.zmq_to_ssl.write(data)

    def send(self, data):
        self.app_to_ssl.write(data)

    def flush(self, io):
        ret = io.getvalue()
        io.truncate(0)
        return ret

    def shutdown(self):
        self.ssl.set_ssl_close_flag(m.m2.bio_close)
        self.ssl.shutdown(
            m.SSL.SSL_RECEIVED_SHUTDOWN | m.SSL.SSL_SENT_SHUTDOWN)
        if hasattr(self, 'rbio'):
            self.rbio.close()
            self.wbio.close()
        self.ssl.close()
        if hasattr(self, 'rbio'):
            del self.rbio
            del self.wbio
        _TLSZmq._ctx = None


class TLSZmqServer(_TLSZmq):

    def __init__(self, identity, cert, key, ca=None, proto='sslv3',
                 verify_loc=None, cert_password=None):
        """
        Creates a TLS/SSL wrapper for handling handshaking and encryption
        of messages over insecure sockets

        Arguments:

        proto       --  Protocol of the wrapper.
                        Valid values are: 'sslv3' or 'tlsv1'.
                        Required.

        identity    --  unique id of the wrapper. Max length is 32 chars, due to
                        limitation in OpenSSL. Needed for proper
                        packet handling. Required.

        cert        --  Certificate file name. Mandatory.

        key         --  File name with PEM-encoded key of the server.
                        Mandatory.

        ca          --  CA certificate file name. Not applicable for clients,
                        Mandatory with server that checks issues client certs.

        verify_loc  --  Verify locations. Certificate file(s) to use to verify
                        client certificates. Used for multi-node setup.

        cert_password --    Certificate private key password

        """
        super(TLSZmqServer, self).__init__(LOGS, proto, 'Server', identity,
                                           cert, key, ca,
                                           verify_loc=verify_loc,
                                           cert_password=cert_password)


class TLSZmqClient(_TLSZmq):

    def __init__(self, proto, cert, key, ca=None, cert_password=None):
        """
        Creates a TLS/SSL wrapper for handling handshaking and encryption
        of messages over insecure sockets

        Arguments:

        proto       --  Protocol of the wrapper.
                        Valid values are: 'sslv3' or 'tlsv1'.
                        Required.

        cert        --  Certificate file name.
                        Usually the client uses a signed certificate from the
                        server's CA.

        key         --  File name with PEM-encoded key of the client.
                        Mandatory with cert.

        ca          --  CA file for server verification

        cert_password --    Certificate private key password

        """
        super(TLSZmqClient, self).__init__(LOGC, type='Client',
                                           cert=cert, key=key, ca=ca,
                                           cert_password=cert_password)


class TLSServerCrypt(object):

    def __init__(self, key, cert_password=None):
        """
        Encrypts server PUB command using servers private key

        Arguments:

        key         --  Server key - PEM-encoded file(e.g. server.key).

        cert_password --    Certificate private key password

        """
        def pass_cb(*args):
            return cert_password

        priv_key = m.BIO.MemoryBuffer(open(key).read())
        self.key = m.RSA.load_key_bio(priv_key, pass_cb)
        del priv_key

    def __del__(self):
        del self.key

    def encrypt(self, *frames):
        json_frames = json.dumps(frames)

        enc_message = self.key.private_encrypt(json_frames,
                                               m.RSA.pkcs1_padding)
        return enc_message


class TLSClientDecrypt(object):

    def __init__(self, server):
        """
        Decrypts Server PUB commands using server's public key

        Arguments:

        server          --  Server cert file (e.g. server.crt).

        """
        server_crt = m.X509.load_cert(server)
        self.rsa = server_crt.get_pubkey().get_rsa()
        del server_crt

    def __del__(self):
        del self.rsa

    def decrypt(self, enc_message):
        payload = enc_message

        dec_message = self.rsa.public_decrypt(payload, m.RSA.pkcs1_padding)

        return json.loads(dec_message)
