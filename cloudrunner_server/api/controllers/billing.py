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
from cloudrunner_server.api.hooks.perm_hook import PermHook
from cloudrunner_server.api.model import User
from cloudrunner_server.api.util import JsonOutput as O


class Billing(HookController):

    __hooks__ = [DbHook(), ErrorHook(), BrainTreeHook(),
                 PermHook(have=set(['is_admin']))]

    @expose('json', generic=True)
    def account(self, *args, **kwargs):
        """
        .. http:get:: /billing/account

            Returns basic account information

            >header:    Auth token
        """
        CS = request.braintree.CustomerSearch
        customers = [c for c in request.braintree.Customer.search(
            CS.company == request.user.org).items]
        if not customers:
            # Try to create customer
            user = User.visible(request).filter(
                User.username == request.user.username).one()
            result = request.braintree.Customer.create({
                "first_name": user.first_name,
                "last_name": user.last_name,
                "company": user.org.name,
                "email": user.email,
                "phone": user.phone,
            })

            if not result.is_success:
                return O.error("Cannot fetch data from billing system")

            customers = [result.customer]

        customer = customers[0]

        card, subs = {}, {}
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
            TS.customer_company == request.user.org])
        return O.billing(transactions=[serialize_t(h) for h in history.items],
                         plan=subs, cards=card)

    @account.when(method='PUT', template='json')
    def update_data(self, *args, **kwargs):
        kwargs = kwargs or request.json
        if "cc" in kwargs:
            cc_data = kwargs['cc']
            CS = request.braintree.CustomerSearch
            customers = [c for c in request.braintree.Customer.search(
                CS.company == request.user.org).items]
            if not customers:
                return O.error("Customer not found")

            customer = customers[0]
            expire_m, expire_y = cc_data['expire_date'].split("/")

            token = ""
            if customer.credit_cards:
                # Update
                cc = customer.credit_cards[0]
                token = cc.token
                result = request.braintree.PaymentMethod.update(token, {
                    "number": cc_data['number'],
                    "cardholder_name": cc_data['cardholder_name'],
                    "expiration_month": expire_m,
                    "expiration_year": expire_y,
                    "cvv": cc_data['cvv'],
                })
            else:
                # Create
                result = request.braintree.CreditCard.create({
                    "customer_id": customer.id,
                    "number": cc_data["number"],
                    "expiration_month": expire_m,
                    "expiration_year": expire_y,
                    "cardholder_name": cc_data['cardholder_name'],
                    "cvv": cc_data['cvv']
                })

            if not result.is_success:
                errors = filter(None, result.errors.deep_errors)
                if errors:
                    return O.error(msg=errors[0].message)
            return O.success(msg="Account updated")

        return O.error(msg="No data provided for update")

    @expose('json')
    def change(self, *args, **kwargs):
        return O.error(msg="Not available yet")


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
