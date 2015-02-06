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

    @expose('json', generic=True)
    def account(self, *args, **kwargs):
        CS = request.braintree.CustomerSearch
        customers = [c for c in request.braintree.Customer.search(
            CS.email == request.user.email).items]
        if not customers:
            return O.error("Customer not found")

        customer = customers[0]

        card, subs = {}, {'name': request.user.tier.name}
        if customer.credit_cards:
            cc = customer.credit_cards[0]
            card['number'] = cc.masked_number
            card['expire'] = cc.expiration_date
            card['type'] = cc.card_type

            if cc.subscriptions:
                sub = cc.subscriptions[0]
                subs['next_date'] = sub.next_billing_date
                subs['next_amount'] = sub.next_billing_period_amount

        TS = request.braintree.TransactionSearch
        history = request.braintree.Transaction.search([
            TS.customer_email == request.user.email])
        return O.billing(transactions=[serialize_t(h) for h in history.items],
                         plan=subs, cards=card)

    @account.when(method='POST', template='json')
    def update(self, *args, **kwargs):
        kwargs = kwargs or request.json
        if "cc" in kwargs:
            cc_data = kwargs['cc']
            CS = request.braintree.CustomerSearch
            customers = [c for c in request.braintree.Customer.search(
                CS.email == request.user.email).items]
            if not customers:
                return O.error("Customer not found")

            customer = customers[0]

            token = ""
            if customer.credit_cards:
                cc = customer.credit_cards[0]
                token = cc.token

            try:
                expire_m, expire_y = cc_data['expire_date'].split("/")
                result = request.braintree.PaymentMethod.update(token, {
                    "number": cc_data['number'],
                    "cardholder_name": cc_data['cardholder_name'],
                    "expiration_month": expire_m,
                    "expiration_year": expire_y,
                    "cvv": cc_data['cvv'],
                })
                if not result.is_success:
                    errors = filter(None, result.errors.deep_errors)
                    if errors:
                        return O.error(msg=errors[0].message)
                return O.success(msg="Account updated")
            except request.braintree.exceptions.not_found_error.NotFoundError:
                return O.success(msg="Payment instrument not found")

        return O.error(msg="No data provided for update")


def serialize_t(item):
    status_code = safe(lambda i: int(i or 0) / 10,
                       item.processor_response_code,
                       default=item.processor_response_code)
    return dict(amount=item.amount, created=item.created_at,
                currency=item.currency_iso_code, id=item.id,
                status=item.processor_response_text,
                status_code=status_code,
                plan=item.plan_id
                )


def safe(func, *args, **kwargs):
    try:
        return func(*args)
    except:
        return kwargs.get("default")
