#!/usr/bin/python
# -*- coding: utf-8 -*-
# vim: tabstop=4 shiftwidth=4 softtabstop=4

# /*******************************************************
#  * Copyright (C) 2013-2014 CloudRunner.io <info@cloudrunner.io>
#  *
#  * Proprietary and confidential
#  * This file is part of CloudRunner Server.
#  *
#  * CloudRunner Server can not be copied and/or distributed without the express
#  * permission of CloudRunner.io
#  *******************************************************/

from cloudrunner.core.message import ScheduleReq
from cloudrunner.util.shell import colors
from cloudrunner.util.loader import local_plugin_loader
from cloudrunner_server.dispatcher import SCHEDULER_URI_TEMPLATE
from cloudrunner_server.plugins.auth.base import NodeVerifier

import fcntl
import M2Crypto as m
import json
import os
import random
import re
from socket import gethostname
import stat
from string import ascii_letters
import time
import zmq

YEARS = 10  # Default expire for signed certificates
TAG = 1
DATA = 2
ERR = 3
NOTE = 4
EMPTY = 5

C = ''
try:
    import locale
    l_c = locale.getdefaultlocale()
    C = l_c[0].rpartition('_')[-1]
except:
    C = 'US'

VALID_NAME = re.compile('^[a-zA-Z0-9\-_\.]+$')


def yield_wrap(func):
    def consume(*args, **kwargs):
        it = func(*args, **kwargs)
        if it:
            return [x for x in it]
        return []
    return consume


class CertController(object):

    def __init__(self, config):
        self.config = config
        self.ca_path = os.path.dirname(
            os.path.abspath(self.config.security.ca))

    def pass_cb(self, *args):
        return self.config.security.cert_pass

    @property
    def serial_no(self):
        serial_fn = os.path.join(self.ca_path, 'serial')
        serial = open(serial_fn).read()
        assert serial
        return int(serial) + 1

    def serial_no_inc(self):
        serial_fn = os.path.join(self.ca_path, 'serial')
        if not os.path.exists(serial_fn):
            serial = open(serial_fn, 'w')
        else:
            serial = os.open(serial_fn, os.O_RDWR)
            current = os.read(serial, 1000)
            os.ftruncate(serial, 0)
            os.lseek(serial, 0, 0)
        if not current:
            current = 0
        fcntl.flock(serial, fcntl.LOCK_EX)
        new_serial = int(current) + 1
        os.write(serial, '%02s' % new_serial)
        os.close(serial)
        return new_serial

    def get_approved_nodes(self, org=None):
        approved = []
        for (_dir, _, nodes) in os.walk(os.path.join(self.ca_path, 'nodes')):
            for node in nodes:
                try:
                    node = node.rsplit('.crt', 1)[0]
                    o, _, node = node.partition('.')
                    if org and o != org:
                        continue
                    if not node:
                        node = o
                    approved.append(node)
                except:
                    pass
        for (_dir, _, nodes) in os.walk(os.path.join(self.ca_path, 'issued')):
            for node in nodes:
                try:
                    node = node.rsplit('.crt', 1)[0]
                    o, _, node = node.partition('.')
                    o, _, node = node.partition('.')
                    if org and o != org:
                        continue
                    if not node:
                        node = o
                    approved.append(node)
                except:
                    pass
        return approved

    @yield_wrap
    def list(self, **kwargs):
        yield TAG, "Pending node requests:"
        total_cnt = 0
        for (_dir, _, reqs) in os.walk(os.path.join(self.ca_path, 'reqs')):
            for req in reqs:
                csr = None
                try:
                    csr = m.X509.load_request(os.path.join(_dir, req))
                    subj = csr.get_subject()
                    if self.config.security.use_org and subj.OU:
                        yield DATA, "%-40s %s" % (subj.CN, subj.OU)
                    else:
                        yield DATA, subj.CN
                    total_cnt += 1
                except:
                    pass
                finally:
                    del csr
        if not total_cnt:
            yield DATA, '--None--'

        total_cnt = 0
        yield TAG, "Approved nodes:"
        for (_dir, _, nodes) in os.walk(os.path.join(self.ca_path, 'nodes')):
            for node in nodes:
                try:
                    if not node.endswith('.crt'):
                        continue
                    node = node.rsplit('.crt', 1)[0]
                    org, _, node = node.partition('.')
                    if not node:
                        node = org
                        org = ''
                    if self.config.security.use_org:
                        yield DATA, "%-40s %s" % (node, org)
                    else:
                        yield DATA, node
                    total_cnt += 1
                except Exception, ee:
                    print ee
                    pass

        for (_dir, _, nodes) in os.walk(os.path.join(self.ca_path, 'issued')):
            for node in nodes:
                try:
                    if not node.endswith('.crt'):
                        continue
                    node = node.rsplit('.crt', 1)[0]
                    org, _, node = node.partition('.')
                    if not node:
                        node = org
                        org = ''
                    if self.config.security.use_org:
                        yield DATA, "%-40s %s" % (node, org)
                    else:
                        yield DATA, node
                    total_cnt += 1
                except Exception, ee:
                    print ee
                    pass
        if not total_cnt:
            yield DATA, '--None--'

    @yield_wrap
    def list_all_approved(self):
        approved_nodes = []
        for (_dir, _, nodes) in os.walk(os.path.join(self.ca_path, 'nodes')):
            for node in nodes:
                try:
                    if not node.endswith('.crt'):
                        continue
                    node = node.rsplit('.crt', 1)[0]
                    org, _, node = node.partition('.')
                    approved_nodes.append(node)
                except:
                    pass
        return approved_nodes

    @yield_wrap
    def list_pending(self, org=None):
        pending_nodes = []
        for (_dir, _, reqs) in os.walk(os.path.join(self.ca_path, 'reqs')):
            for req in reqs:
                csr = None
                try:
                    csr = m.X509.load_request(os.path.join(_dir, req))
                    subj = csr.get_subject()
                    if not org or subj.O == org:
                        pending_nodes.append(subj.CN)
                except:
                    pass
                finally:
                    del csr
        return pending_nodes

    @yield_wrap
    def sign(self, node=None, **kwargs):
        if node:
            for n in node:
                messages, _ = self.sign_node(n, **kwargs)
                for line in messages:
                    yield line

    def sign_node(self, node, **kwargs):
        is_signed = False
        messages = []

        for (_dir, _, reqs) in os.walk(os.path.join(self.ca_path, 'reqs')):
            for req in reqs:
                csr = None
                cert = None
                ca_key = None
                ca_priv_key = None
                now = None
                nowPlusYear = None
                try:
                    csr = m.X509.load_request(os.path.join(_dir, req))
                    if node == csr.get_subject().CN:
                        ca = kwargs.get('ca', '')
                        if self.config.security.use_org and not ca:
                            if kwargs.get('auto'):
                                # Load from CSR
                                ca = csr.get_subject().OU
                                if not ca:
                                    messages.append(
                                        (ERR, "OU is not found in CSR subject"))
                                    return messages, None
                            else:
                                for verifier in NodeVerifier.__subclasses__():
                                    ca = verifier(
                                        self.config).verify(node, csr)
                                    if ca:
                                        break
                                else:
                                    messages.append((
                                        ERR, "CA is mandatory for "
                                        "signing a node"))
                                    return messages, None
                        if not self.config.security.use_org and ca:
                            messages.append((
                                ERR, "Although CA value is passed, "
                                "it will be skipped for No-org setup."))

                        # Validate names
                        if not VALID_NAME.match(node):
                            messages.append((ERR, "Invalid node name"))
                            return messages, None
                        if self.config.security.use_org and \
                            not VALID_NAME.match(ca):
                            messages.append((ERR, "Invalid org name"))
                            return messages, None

                        if not csr.get_subject().OU:
                            messages.append((ERR, "subject.OU is empty"))
                            return messages, None

                        messages.append((TAG, "Signing %s" % node))
                        if ca:
                            ca_cert_file = os.path.join(self.ca_path, 'org',
                                                        ca + '.ca.crt')
                            if not os.path.exists(ca_cert_file):
                                messages.append((
                                    ERR, "No CA certificate found "
                                    "for %s" % ca))
                                return messages, None
                            try:
                                ca_priv_key = m.RSA.load_key(
                                    os.path.join(self.ca_path, 'org',
                                                 ca + '.key'),
                                    self.pass_cb)
                            except Exception, ca_ex:
                                messages.append((
                                    ERR, "Cannot load Sub-CA cert: %s" % ca_ex))
                                return messages, None

                        else:
                            # Use Master CA
                            ca_cert_file = self.config.security.ca
                            ca_priv_key = m.RSA.load_key(
                                os.path.join(self.ca_path, 'ca.key'),
                                self.pass_cb)

                        ca_crt = m.X509.load_cert(ca_cert_file)

                        ca_key = m.EVP.PKey()
                        ca_key.assign_rsa(ca_priv_key)
                        ca_crt.set_pubkey(ca_key)

                        cert = m.X509.X509()
                        cert.set_version(2)
                        ser_no = self.serial_no_inc()
                        messages.append((TAG, "Setting serial to %d" % ser_no))
                        cert.set_serial_number(ser_no)
                        csr_subj = csr.get_subject()
                        cert.get_subject().C = csr_subj.C
                        cert.get_subject().CN = csr_subj.CN
                        if ca:
                            cert.get_subject().O = ca
                        cert.set_issuer(ca_crt.get_subject())
                        t = long(time.time()) + time.timezone
                        now = m.ASN1.ASN1_UTCTIME()
                        now.set_time(t)
                        nowPlusYear = m.ASN1.ASN1_UTCTIME()
                        nowPlusYear.set_time(t + 60 * 60 * 24 * 365 * YEARS)
                        cert.set_not_before(now)
                        cert.set_not_after(nowPlusYear)
                        cert.set_pubkey(csr.get_pubkey())

                        res = cert.sign(ca_key, 'sha1')
                        assert cert.verify(ca_crt.get_pubkey())

                        if res < 0:
                            messages.append((ERR, "Sign failed"))
                        else:
                            if not os.path.exists(os.path.join(self.ca_path,
                                                               'issued')):
                                os.makedirs(os.path.join(self.ca_path,
                                                         'issued'))
                            cert_file_name = os.path.join(
                                self.ca_path, 'issued',
                                '.'.join([csr.get_subject().OU, node, 'crt']))
                            cert.save_pem(cert_file_name)
                            os.chmod(
                                cert_file_name, stat.S_IREAD | stat.S_IWRITE)
                            cert.save_pem(cert_file_name)
                            is_signed = True
                            os.unlink(os.path.join(_dir, req))
                            messages.append((DATA, "%s signed" % node))
                            messages.append((DATA,
                                             "Issuer %s" % cert.get_issuer()))
                            messages.append((DATA,
                                             "Subject %s" % cert.get_subject()))
                            return messages, cert_file_name
                except Exception, ex:
                    print "Error: %r" % ex
                    messages.append((ERR, "Error: %r" % ex))
                finally:
                    del csr
                    del cert
                    del ca_key
                    del ca_priv_key
                    del now
                    del nowPlusYear

        if not is_signed:
            messages.append((EMPTY, "Nothing found to sign for %s" % node))
        return messages, None

    def _ensure_autosign(self):
        autosign = os.path.join(self.ca_path, 'autosign')
        if not os.path.exists(autosign):
            # Create
            with open(autosign, 'w') as f:
                f.write("")

    def can_approve(self, node_name):
        if self.config.security.auto_approve:
            return True

        autosign = os.path.join(self.ca_path, 'autosign')
        self._ensure_autosign()

        data = open(autosign).read()
        if data:
            try:
                data = json.loads(data)
            except:
                data = {}
        else:
            data = {}
        auto_sign = node_name in data and data[node_name] > time.time()
        if auto_sign:
            return True

    @yield_wrap
    def autosign(self, node=None, **kwargs):
        autosign = os.path.join(self.ca_path, 'autosign')
        self._ensure_autosign()

        data = open(autosign).read()
        if data:
            try:
                data = json.loads(data)
            except:
                data = {}
        else:
            data = {}
        data[node] = time.time() + int(kwargs.get('expire', '30')) * 60
        f = open(autosign, 'w')
        f.write(json.dumps(data))
        f.close()
        yield TAG, "Set autosign to %s" % node

    @yield_wrap
    def revoke(self, node, **kwargs):
        for n in node:
            ca = kwargs.get('ca')
            if self.config.security.use_org and not ca:
                yield ERR, "ORG param is required to revoke"
                return
            if ca:
                yield TAG, "Revoking certificate for %s:%s" % (ca, n)
            else:
                ca = 'DEFAULT'
                yield TAG, "Revoking certificate for ", n

            cert_fn = os.path.join(
                self.ca_path, 'nodes', '%s.%s.crt' % (ca, n))
            if os.path.exists(cert_fn):
                ser_no = open(cert_fn).read().strip()
                assert int(ser_no)
                # Update CRL file
                crl_file = open(os.path.join(self.ca_path, 'crl'), 'w')
                fcntl.flock(crl_file, fcntl.LOCK_EX)
                crl_file.write('%s\n' % ser_no)
                crl_file.close()
                yield DATA, "Removing signed certificate found for %s " % n
                os.unlink(cert_fn)
            issued_fn = os.path.join(
                self.ca_path, 'issued', '%s.%s.crt' % (ca, n))
            if os.path.exists(issued_fn):
                yield DATA, "Removing issued certificate found for %s " % n
                os.unlink(issued_fn)

            yield DATA, "Certificate for node [%s] revoked" % n

    @yield_wrap
    def clear_req(self, node, **kwargs):
        for n in node:
            ca = kwargs.get('ca')
            if self.config.security.use_org and not ca:
                yield ERR, "OEG param is required to revoke"
                return
            if ca:
                yield TAG, "Clearing requests for %s:%s" % (ca, n)
            else:
                yield TAG, "Clearing requests for ", n

            req_fn = os.path.join(
                self.ca_path, 'reqs', '%s.%s.csr' % (ca, n))
            if not os.path.exists(req_fn):
                yield DATA, "No pending request found for %s " % n
                return

            os.unlink(req_fn)
            yield DATA, "Request for node [%s] deleted" % n

    @yield_wrap
    def create_ca(self, ca, **kwargs):
        if not os.path.exists(self.config.security.ca):
            yield ERR, "CA key missing, probably Master is not configured yet"
            return

        yield TAG, "Generating intermediate CA"

        ca_dir = os.path.join(self.ca_path, 'org')
        if not os.path.exists(ca_dir):
            os.makedirs(ca_dir)
        if not os.path.exists(os.path.join(ca_dir, 'certs')):
            os.makedirs(os.path.join(ca_dir, 'certs'))
        if not os.path.exists(os.path.join(ca_dir, 'newcerts')):
            os.makedirs(os.path.join(ca_dir, 'newcerts'))
        if not os.path.exists(os.path.join(ca_dir, 'index.txt')):
            open(os.path.join(ca_dir, 'index.txt'), 'w').write('')
        if not os.path.exists(os.path.join(ca_dir, 'serial')):
            open(os.path.join(ca_dir, 'serial'), 'w').write('1000')

        conf_file = os.path.join(ca_dir, "openssl.cnf")
        if not os.path.exists(conf_file):
            conf = """
[ca]
default_ca      = CloudRunner CA

[CloudRunner CA]
dir             = %(dir)s
certs           = %(dir)s/certs
new_certs_dir   = %(dir)s/newcerts
database        = %(dir)s/index.txt
serial          = %(dir)s/serial
policy          = policy_match
x509_extensions = usr_cert
default_days    = %(days)s
private_key     = %(par_dir)s/ca.key
certificate     = %(par_dir)s/ca.crt
default_md      = sha1

[policy_match]
countryName             = supplied
stateOrProvinceName     = optional
organizationName        = supplied
organizationalUnitName  = optional
commonName              = supplied
emailAddress            = optional

[req]
default_bits            = 2048
default_keyfile         = privkey.pem
distinguished_name      = req_distinguished_name
attributes              = req_attributes
x509_extensions = v3_ca # The extentions to add to the self signed cert

[v3_ca]
subjectKeyIdentifier=hash
authorityKeyIdentifier=keyid:always,issuer
basicConstraints = CA:true

""" % dict(dir=ca_dir, par_dir=self.ca_path, days=365 * YEARS)

            open(conf_file, 'w').write(conf)

        ca_priv_key_file = os.path.join(self.ca_path, 'ca.key')
        ca_priv_key = m.RSA.load_key(os.path.join(self.ca_path, 'ca.key'),
                                     self.pass_cb)
        subca_priv_key_file = os.path.join(self.ca_path, 'org', ca + '.key')
        ca_cert_file = os.path.join(self.ca_path, 'ca.crt')
        subca_csr_file = os.path.join(ca_dir, ca + ".csr")
        subca_crt_file = os.path.join(ca_dir, ca + ".ca.crt")

        subca_key = m.EVP.PKey()
        subca_rsa = m.RSA.gen_key(kwargs.get('key_size', 2048),
                                  65537,
                                  lambda: True)
        subca_key.assign_rsa(subca_rsa)

        subca_csr = m.X509.Request()
        try:
            subca_csr.set_pubkey(subca_key)
        except Exception, ex:
            print ex
        #subca_rsa = None
        subca_key.save_key(subca_priv_key_file,
                           callback=lambda x: self.config.security.cert_pass)
        os.chmod(subca_priv_key_file, stat.S_IREAD | stat.S_IWRITE)

        s_subj = subca_csr.get_subject()
        s_subj.O = ca
        s_subj.CN = ca
        s_subj.C = C
        try:
            subca_csr.sign(subca_key, 'sha1')
        except Exception, ex:
            print ex

        subca_pub = subca_csr.get_pubkey()
        assert subca_csr.verify(subca_pub)
        subca_csr.save_pem(subca_csr_file)
        os.chmod(subca_csr_file, stat.S_IREAD | stat.S_IWRITE)

        create_interm_ca = ('openssl ca -extensions v3_ca '
                            '-config %s '
                            '-keyfile "%s" '
                            '-cert "%s" '
                            '-in "%s" '
                            '-out "%s" '
                            '-subj "%s" '
                            '-passin pass:%s '
                            '-notext -md sha1 -batch' %
                           (conf_file,
                            ca_priv_key_file,
                            ca_cert_file,
                            subca_csr_file,
                            subca_crt_file,
                            str(s_subj),
                            self.config.security.cert_pass))
        ret = os.system(create_interm_ca)
        os.unlink(subca_csr_file)
        if ret:
            yield ERR, 'Error creating Org CA: %s' % ret
            exit(1)
        yield DATA, 'Done'

    @yield_wrap
    def list_ca(self, **kwargs):
        if not os.path.exists(self.config.security.ca):
            yield ERR, "CA key missing, probably Master is not configured yet"
            return

        ca_dir = os.path.join(self.ca_path, 'org')
        if not os.path.exists(ca_dir):
            yield TAG, "No organization CA certificates found"
            return
        _, _, files = next(os.walk(ca_dir))
        for _file in files:
            if _file.endswith('.ca.crt'):
                yield DATA, _file.replace('.ca.crt', '')

    @yield_wrap
    def revoke_ca(self, ca, **kwargs):
        org_path = os.path.join(self.ca_path, 'org')
        ca_key = os.path.join(org_path, ca + '.key')
        ca_crt = os.path.join(org_path, ca + '.ca.crt')
        if not os.path.exists(ca_crt):
            yield ERR, "No CA certificate found"
            return
        conf_file = os.path.join(org_path, "openssl.cnf")

        ret = os.system("openssl ca -revoke %s -config %s -passin pass:%s" %
                       (ca_crt, conf_file, self.config.security.cert_pass))
        if ret:
            yield ERR, 'Error revoking Org CA: %s' % ret
            exit(1)

        yield DATA, "Removing crt file %s" % ca_crt
        os.unlink(ca_crt)
        yield DATA, "Removing key file %s" % ca_key
        os.unlink(ca_key)

        yield TAG, "Certificate for %s removed" % ca


class ConfigController(object):

    def __init__(self, config):
        self.config = config

    @yield_wrap
    def create(self, **kwargs):
        cert = CertController(self.config)
        yield TAG, "Creating new configuration"
        ca_path = kwargs.get('path', None)
        if not ca_path:
            if self.config.security.ca:
                ca_path = os.path.dirname(os.path.abspath(
                    self.config.security.ca))
            else:
                ca_path = '/etc/cloudrunner/CA'

        if os.path.exists(ca_path):
            for (dir, _, files) in os.walk(ca_path):
                if files:
                    if not kwargs.get('overwrite', False):
                        yield ERR, 'The dir %s already exists and ' \
                            'is not empty. To force creation of ' \
                            'new certificates there, use the ' \
                            '--overwrite options' % ca_path
                        return
                    else:
                        yield DATA, 'Overwriting existing files in %s' % \
                            ca_path
                        break
        else:
            # Create it
            os.makedirs(ca_path)

        serial = 1
        serial_fn = os.path.join(ca_path, 'serial')
        open(serial_fn, 'w').write('%02d' % serial)
        os.chmod(serial_fn, stat.S_IREAD | stat.S_IWRITE)

        cert_password = ''.join([random.choice(ascii_letters)
                                 for x in range(32)])

        reqs_dir = os.path.join(ca_path, 'reqs')
        if not os.path.exists(reqs_dir):
            yield TAG, "Creating: ", reqs_dir
            os.makedirs(reqs_dir)
        nodes_dir = os.path.join(ca_path, 'nodes')
        if not os.path.exists(nodes_dir):
            yield TAG, "Creating: ", nodes_dir
            os.makedirs(nodes_dir)
        issued_dir = os.path.join(ca_path, 'issued')
        if not os.path.exists(issued_dir):
            yield TAG, "Creating: ", issued_dir
            os.makedirs(issued_dir)
        subca_dir = os.path.join(ca_path, 'org')
        if not os.path.exists(subca_dir):
            yield TAG, "Creating: ", subca_dir
            os.makedirs(subca_dir)

        # set 600 on dirs
        os.chmod(ca_path, stat.S_IRWXU)
        os.chmod(reqs_dir, stat.S_IRWXU)
        os.chmod(nodes_dir, stat.S_IRWXU)

        CN = self.config.id or gethostname()

        ca_key_file = os.path.join(ca_path, 'ca.key')
        ca_crt_file = os.path.join(ca_path, 'ca.crt')
        key_file = os.path.join(ca_path, 'server.key')
        csr_file = os.path.join(ca_path, 'server.csr')
        crt_file = os.path.join(ca_path, 'server.crt')

        # Certificates/Keys generation

        # CA key
        ca_key = m.EVP.PKey()
        ca_priv = m.RSA.gen_key(kwargs.get('key_size', 2048),
                                65537,
                                lambda: True)
        ca_key.assign_rsa(ca_priv)
        ca_priv = None

        # CA csr
        ca_req = m.X509.Request()
        ca_req.set_pubkey(ca_key)

        ca_subj = ca_req.get_subject()
        ca_subj.CN = 'CloudRunner Master CA'
        ca_subj.C = C
        ca_req.sign(ca_key, 'sha1')
        assert ca_req.verify(ca_key)

        ca_pub = ca_req.get_pubkey()

        # CA cert
        '''

        ### M2Crypto has bug for adding 'authorityKeyIdentifier extension
        ### https://bugzilla.osafoundation.org/show_bug.cgi?id=7530
        ### https://bugzilla.osafoundation.org/show_bug.cgi?id=12151
        ### So create CA crt using OpenSSL tool ...

        ca_crt = m.X509.X509()
        ca_crt.set_serial_number(serial)
        serial += 1
        open(serial_fn, 'w').write('%02d' % serial)
        ca_crt.set_version(2)
        ca_crt.set_subject(ca_subj)

        t = long(time.time()) + time.timezone
        now = m.ASN1.ASN1_UTCTIME()
        now.set_time(t)
        nowPlusYear = m.ASN1.ASN1_UTCTIME()
        nowPlusYear.set_time(t + 60 * 60 * 24 * 365 * YEARS)
        ca_crt.set_not_before(now)
        ca_crt.set_not_after(nowPlusYear)

        issuer = m.X509.X509_Name()
        issuer.C = C
        issuer.CN = "CloudRunner Master CA"

        ca_crt.set_issuer(issuer)
        ca_crt.set_pubkey(ca_pub)
        ca_crt.add_ext(m.X509.new_extension(
            'basicConstraints', 'CA:TRUE'))
        ca_crt.add_ext(m.X509.new_extension('subjectKeyIdentifier',
                                            ca_crt.get_fingerprint()))
        #ca_crt.add_ext(m.X509.new_extension('authorityKeyIdentifier',
        #                                    'keyid:always', 0))

        ca_crt.sign(ca_key, 'sha1')
        ca_crt.check_ca()
        assert ca_crt.verify()
        assert ca_crt.verify(ca_pub)
        assert ca_crt.verify(ca_crt.get_pubkey())

        '''
        yield TAG, "Saving CA KEY file %s" % ca_key_file
        ca_key.save_key(ca_key_file, callback=lambda x: cert_password)
        os.chmod(ca_key_file, stat.S_IREAD | stat.S_IWRITE)

        ret = os.system('openssl req -new -x509 -days %s -key "%s" '
                        '-out "%s" -subj "/C=%s/CN=%s" -passin pass:%s' %
                       (365 * YEARS, ca_key_file, ca_crt_file,
                        ca_subj.C, ca_subj.CN, cert_password))

        if ret:
            yield ERR, 'Error running openssl for CA crt: %s' % ret
            exit(1)

        yield TAG, "Saving CA CRT file %s" % ca_crt_file
        # print ca_crt.as_text()
        # ca_crt.save_pem(ca_crt_file)
        os.chmod(ca_crt_file, stat.S_IREAD | stat.S_IWRITE)

        # Server key
        server_key = m.EVP.PKey()
        s_rsa = m.RSA.gen_key(kwargs.get('key_size', 2048),
                              65537,
                              lambda: True)
        server_key.assign_rsa(s_rsa)
        s_rsa = None

        ca_pub = ca_req.get_pubkey()

        # Server csr
        server_req = m.X509.Request()
        server_req.set_pubkey(server_key)

        s_subj = server_req.get_subject()
        s_subj.CN = 'CloudRunner Master'
        s_subj.C = C
        server_req.sign(server_key, 'sha1')

        server_pub = server_req.get_pubkey()
        assert server_req.verify(server_pub)

        # Server cert
        server_crt = m.X509.X509()
        server_crt.set_serial_number(serial)
        serial += 1
        open(serial_fn, 'w').write('%02d' % serial)
        server_crt.set_version(2)
        server_crt.set_subject(s_subj)

        t = long(time.time()) + time.timezone
        now = m.ASN1.ASN1_UTCTIME()
        now.set_time(t)
        nowPlusYear = m.ASN1.ASN1_UTCTIME()
        nowPlusYear.set_time(t + 60 * 60 * 24 * 365 * YEARS)
        server_crt.set_not_before(now)
        server_crt.set_not_after(nowPlusYear)

        issuer = m.X509.X509_Name()
        issuer.C = C
        issuer.CN = "CloudRunner Master CA"

        server_crt.set_issuer(issuer)
        server_crt.set_pubkey(server_pub)
        server_crt.set_pubkey(server_crt.get_pubkey())  # Test

        server_crt.sign(ca_key, 'sha1')
        assert server_crt.verify(ca_pub)
        assert server_crt.verify(ca_key)

        yield TAG, "Saving Server CRT file %s" % crt_file
        # print server_crt.as_text()
        server_crt.save_pem(crt_file)
        os.chmod(crt_file, stat.S_IREAD | stat.S_IWRITE)

        yield TAG, "Saving Server KEY file %s" % key_file
        server_key.save_key(key_file, callback=lambda x: cert_password)
        os.chmod(key_file, stat.S_IREAD | stat.S_IWRITE)

        yield TAG, "Updating config settings"

        self.config.update('Security', 'server_cert', crt_file)
        self.config.update('Security', 'server_key', key_file)
        self.config.update('Security', 'ca', ca_crt_file)
        self.config.update('Security', 'cert_pass', cert_password)
        self.config.reload()

        yield TAG, "IMPORTANT !!! READ CAREFULLY !!!"
        yield NOTE, 'Keep your CA key file(%s) in a secure place. ' \
            'It is needed to sign node certificates and to reissue ' \
            'the Server certificate when it expires[(%s)]. ' \
            'Compromising it may allow an attacker to sign a false ' \
            'certificate and to wrongfully connect to the Server.' % \
            (ca_key_file, nowPlusYear)
        yield NOTE, "IMPORTANT !!! READ CAREFULLY !!!"

        yield TAG, "Configuration completed"

        del ca_key
        del ca_req
        del server_req
        del server_key
        del server_crt
        del now
        del nowPlusYear

    @yield_wrap
    def check(self, **kwargs):
        if not os.path.exists(self.config.security.ca):
            self.create(**kwargs)
            yield TAG, "Configuration successful"
        else:
            yield TAG, "Already configured"

    @yield_wrap
    def show(self, **kwargs):
        yield TAG, "Master configuration"
        yield TAG, "=" * 50

        yield DATA, "Config file [%s]" % self.config._fn

        ca_path = os.path.dirname(self.config.security.ca)
        if os.path.exists(ca_path):
            yield DATA, "CA path [%s]" % ca_path
        else:
            yield ERR, "CA path [%s]" % ca_path, ' [Dir missing]'

        if os.path.exists(self.config.security.ca):
            yield DATA, "CA certificate [%s]" % self.config.security.ca
        else:
            yield ERR, "CA certificate [%s]" % self.config.security.ca, \
                ' [File missing]'

        if os.path.exists(self.config.security.server_key):
            yield DATA, "Server private key [%s]" % \
                self.config.security.server_key
        else:
            yield ERR, "Server private key [%s]" % \
                self.config.security.server_key, ' [File missing]'

        if os.path.exists(self.config.security.server_cert):
            yield DATA, "Server certificate [%s]" % \
                self.config.security.server_cert
        else:
            yield ERR, "Server certificate [%s]" % \
                self.config.security.server_cert, \
                ' [File missing]'

        yield TAG, "Nodes:"
        for node in CertController(self.config).list():
            yield node
        yield TAG, "=" * 50

    @yield_wrap
    def set(self, **kwargs):
        k_v = kwargs.get('Section.key=value', None)
        if k_v:
            item, _, val = k_v.partition('=')
            section, _, key = item.partition('.')
            if section and key:
                section = section.title()
                self.config.update(section, key, val)
                yield TAG, "Set"
                return
        yield ERR, "Not set"

    @yield_wrap
    def get(self, **kwargs):
        item = kwargs.get('Section.key', None)
        if item:
            section, _, key = item.partition('.')
            if section and key:
                section = section.lower()
                _section = getattr(self.config, section)
                if not _section:
                    yield ERR, "Section %s not found!" % section
                    return
                yield TAG, '%s=%s' % (item, getattr(_section, key))
                return
        yield ERR, "Not set"


class SchedulerController(object):

    def __init__(self, config):
        self.config = config
        if self.config.scheduler:
            scheduler_class = local_plugin_loader(self.config.scheduler)
        else:
            print colors.red("=" * 50, bold=1)
            print colors.red("Cannot find scheduler class. "
                             "Set it in config file.", bold=1)
            print colors.red("=" * 50, bold=1)
            exit(1)
        if self.config.transport:
            self.backend_class = local_plugin_loader(self.config.transport)
        else:
            print colors.red("=" * 50, bold=1)
            print colors.red("Cannot find backend transport class. "
                             "Set it in config file.", bold=1)
            print colors.red("=" * 50, bold=1)
            exit(1)

        self.scheduler = scheduler_class()

    @yield_wrap
    def list(self, **kwargs):
        success, jobs = self.scheduler.list(**kwargs)
        output = [', '.join([': '.join([k, str(v)])
                            for k, v in job.items()]) for job in jobs]
        yield DATA, output

    @yield_wrap
    def run(self, job_id, **kwargs):
        '''
        Run Cloudrunner script from scheduled task.
        Usually invoked from CronTab or other scheduler.
        '''
        _req = ScheduleReq('schedule', job_id)
        scheduler_queue = None
        try:
            backend = self.backend_class(self.config)
            scheduler_queue = backend.publish_queue('scheduler')
            scheduler_queue.send(*_req.pack())
            yield DATA, "Job %s sent for execution" % job_id
        except Exception, ex:
            yield ERR, str(ex)
        finally:
            if scheduler_queue:
                scheduler_queue.close()


class UserController(object):

    def __init__(self, config, to_print=True):
        self.config = config

        if self.config.auth:
            auth_class = local_plugin_loader(self.config.auth)
        else:
            print colors.red("=" * 50, bold=1)
            print colors.red("Cannot find auth class. "
                             "Set it in config file.", bold=1)
            print colors.red("=" * 50, bold=1)
            raise Exception("Error loading Auth module")

        self.auth = auth_class(self.config)

    @yield_wrap
    def list(self, **kwargs):
        users = self.auth.list_users()
        yield DATA, users

    @yield_wrap
    def list_orgs(self, **kwargs):
        orgs = self.auth.list_orgs()
        yield DATA, orgs

    @yield_wrap
    def roles(self, username, **kwargs):
        roles = self.auth.user_roles(username).items()
        if not roles:
            yield EMPTY, "No roles for user"

        for node, role in roles:
            yield DATA, '%s => %s' % (node, role)

    @yield_wrap
    def create(self, username, password, org=None, **kwargs):
        success, msg = self.auth.create_user(username, password, org)
        if not success:
            yield ERR, msg
        else:
            yield DATA, msg

    @yield_wrap
    def create_org(self, name, **kwargs):
        success, msg = self.auth.create_org(name)
        if not success:
            yield ERR, msg
        else:
            yield DATA, msg

    @yield_wrap
    def activate_org(self, name, **kwargs):
        success, msg = self.auth.activate_org(name)
        if not success:
            yield ERR, msg
        else:
            yield DATA, msg

    @yield_wrap
    def deactivate_org(self, name, **kwargs):
        success, msg = self.auth.deactivate_org(name)
        if not success:
            yield ERR, msg
        else:
            yield DATA, msg

    @yield_wrap
    def remove_org(self, name, **kwargs):
        success, msg = self.auth.remove_org(name)
        if not success:
            yield ERR, msg
        else:
            yield DATA, msg

    @yield_wrap
    def remove(self, username, **kwargs):
        success, msg = self.auth.remove_user(username)
        if not success:
            yield ERR, msg
        else:
            yield DATA, msg

    @yield_wrap
    def add_role(self, username, node, role, **kwargs):
        success, msg = self.auth.add_role(username, node, role)
        if not success:
            yield ERR, msg
        else:
            yield DATA, msg

    @yield_wrap
    def rm_role(self, username, node, **kwargs):
        success, msg = self.auth.remove_role(username, node)
        if not success:
            yield ERR, msg
        else:
            yield DATA, msg


class TriggerController(object):

    def __init__(self, config, to_print=True):
        self.config = config

    def fire(self, signal, **kwargs):
        yield TAG, "Firing signal [%s]" % signal

    def attach(self, signal, target, **kwargs):
        yield TAG, "Attaching to signal [%s]" % signal

    def detach(self, signal, target, **kwargs):
        yield TAG, "Detaching to signal [%s]" % signal
