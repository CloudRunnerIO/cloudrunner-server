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

from sqlalchemy import (Column, Integer, String, DateTime, Boolean, ForeignKey)
from sqlalchemy.sql.expression import func
from sqlalchemy.orm import relationship, backref
from .base import TableBase
from .users import User


class Billing(TableBase):
    __tablename__ = 'billing'

    id = Column(Integer, primary_key=True)
    payment_token = Column(String(255), unique=True)
    created_at = Column(DateTime, default=func.now())
    retired_at = Column(DateTime)
    active = Column(Boolean)
    subscription = Column(String(255))
    subscription_name = Column(String(255))

    user_id = Column(Integer, ForeignKey(User.id))

    user = relationship(User, backref=backref('billing'))


class AddOn(TableBase):
    __tablename__ = 'billing_addons'

    id = Column(Integer, primary_key=True)
    addon_name = Column(String(255))
    created_at = Column(DateTime, default=func.now())
    retired_at = Column(DateTime)
    active = Column(Boolean)

    billing_id = Column(Integer, ForeignKey(Billing.id))

    billing = relationship(Billing, backref=backref('addons'))
