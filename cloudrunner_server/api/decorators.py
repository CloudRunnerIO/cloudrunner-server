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

from functools import wraps, partial
import logging
import re
from sqlalchemy.exc import IntegrityError
from pecan import request, response, core

from cloudrunner_server.api.util import JsonOutput as O
from cloudrunner_server.api.model.exceptions import QuotaExceeded

LOG = logging.getLogger()
DUPL_SEARCH = re.compile(r'\'(.*)-\d+')
DUPL_SEARCH2 = re.compile("DETAIL:\s+Key\s*\((\w+)\)=\((.*)\)")


def wrap_command(model=None, model_name=None, method=None, key_error=None,
                 generic_error=None, integrity_error=None, dup_key_index=0):

    def decorator(f):
        kw = dict(model=model,
                  key_error=None,
                  generic_error=None,
                  integrity_error=None)
        f.wrap_create = partial(wrap_command, method='create', **kw)
        f.wrap_update = partial(wrap_command, method='update', **kw)
        f.wrap_delete = partial(wrap_command, method='delete', **kw)
        f.wrap_modify = partial(wrap_command, method='modify', **kw)

        @wraps(f)
        def wrapper(*args, **kwargs):
            # Call function
            try:
                ret = f(*args, **kwargs)

                if ret and ret.get('error'):
                    return ret
                _m = None
                _id = None
                if hasattr(request, '_model_id'):
                    _id = request._model_id
                else:
                    if method == 'create':
                        for m in request.db.new:
                            if isinstance(m, model):
                                _m = m
                                break

                    elif method == 'delete':
                        for m in request.db.deleted:
                            if isinstance(m, model):
                                _id = m.id
                                break

                    elif method in ('update', 'modify'):
                        for m in request.db.dirty:
                            if isinstance(m, model):
                                _id = m.id
                                break
                    request.db.commit()
                    if method == 'create' and _m:
                        _id = _m.id

                if _id:
                    ev_action = "%s:%s" % (model.__tablename__, method)
                    response.fire_up_event = ev_action
                    response.fire_up_id = _id

                if not ret:
                    return O.success(status='ok')
                return ret
            except KeyError, kerr:
                request.db.rollback()
                if key_error and callable(key_error):
                    return key_error(kerr)
                return O.error(msg="Field not present: %s" % kerr,
                               field=str(kerr))

            except IntegrityError, ierr:
                request.db.rollback()
                LOG.error(ierr)
                if integrity_error and callable(integrity_error):
                    return integrity_error(ierr)

                try:
                    try_find = DUPL_SEARCH2.findall(str(ierr.orig))
                    if try_find and len(try_find[0]) == 2:
                        msg = "Duplicate value for '%s': %s" % try_find[0]
                    elif isinstance(ierr.orig.args,
                                    tuple) and len(ierr.orig.args) > 1:
                        if ierr.orig.args[0] == 1062:
                            msg = "Duplicate entry: %s" % (
                                DUPL_SEARCH.findall(
                                    ierr.orig.args[1])[dup_key_index])
                        else:
                            msg = ierr.orig.args[1]
                    elif hasattr(ierr.orig, 'message'):
                        # generic
                        msg = "Duplicate entry into database. Check data"
                except:
                    msg = "Duplicate entry into database. Check data"
                return O.error(msg=msg, reason='duplicate')

            except QuotaExceeded, qe:
                request.db.rollback()
                if generic_error and callable(generic_error):
                    return generic_error(qe)
                return O.error(msg=qe.msg, model=qe.model)

            except core.exc.HTTPNotModified:
                raise

            except Exception, ex:
                if hasattr(request, 'db'):
                    request.db.rollback()
                LOG.exception(ex)
                if generic_error and callable(generic_error):
                    return generic_error(ex)
                return O.error(msg="Cannot %s %s" % (
                    method or "display", model_name or model.__tablename__))

        return wrapper

    return decorator
