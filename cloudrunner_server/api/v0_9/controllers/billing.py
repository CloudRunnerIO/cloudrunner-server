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

from pecan import expose, request
from pecan.hooks import HookController

from cloudrunner_server.api.hooks.braintree_hook import BrainTreeHook
from cloudrunner_server.api.hooks.db_hook import DbHook
from cloudrunner_server.api.hooks.error_hook import ErrorHook
from cloudrunner_server.api.util import JsonOutput as O


class Billing(HookController):

    __hooks__ = [DbHook(), ErrorHook(), BrainTreeHook()]

    @expose('json')
    def token(self):
        token = request.braintree.ClientToken.generate()
        return O.billing(token=token)

    @expose('json')
    def account(self):
        request.user.email = '3tisho433433343@imageo.net'

        CS = request.braintree.CustomerSearch
        customers = [c for c in request.braintree.Customer.search(
            CS.email == request.user.email).items]
        if not customers:
            return O.error("Customer not found")
        customer = customers[0]

        card, subs = {}, {}
        if customer.credit_cards:
            cc = customer.credit_cards[0]
            card['number'] = cc.masked_number
            card['expire'] = cc.expiration_date
            card['cardholder'] = cc.cardholder_name

            if cc.subscriptions:
                sub = cc.subscriptions[0]
                subs['next_date'] = sub.next_billing_date
                subs['next_amount'] = sub.next_billing_period_amount

        TS = request.braintree.TransactionSearch
        history = request.braintree.Transaction.search([
            TS.customer_email == request.user.email])
        return O.billing(transactions=[serialize_t(h) for h in history.items],
                         plans=subs, cards=card)


def serialize_t(item):
    return dict(amount=item.amount, created=item.created_at,
                currency=item.currency_iso_code, id=item.id,
                status=item.processor_response_text,  # , type=item.type
                )
