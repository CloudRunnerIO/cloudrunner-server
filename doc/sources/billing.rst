Billing module
=====================


.. http:get:: /billing/account/

  Load basic billing info

  **Example response**:

  .. sourcecode:: http

      HTTP/1.1 200 OK
      Content-Type: application/json; charset=UTF-8

      {
        "billing": {
          "cards": {
            "expire": "11/2015",
            "type": "MasterCard",
            "number": "555555******4444"},
          "plan": {},
          "transactions": []
        }
      }

  :requestheader X-Cr-User: User name
  :requestheader X-Cr-Token: Auth token

  :statuscode 200: no error



.. http:put:: /billing/account/

  Update payment info

  **Example request**:

   .. sourcecode:: http

      PUT /billing/account HTTP/1.1
      Host: api.cloudrunner.io
      Accept: application/json

      {
        "cc": {
            "cardholder_name": "John Doe",
            "cvv": "134",
            "number": "4111111111111111",
            "expire_date": "11/21"
          }
      }

  **Example response**:

  .. sourcecode:: http

      HTTP/1.1 200 OK
      Content-Type: application/json; charset=UTF-8

      {
        "success": {
          "msg": "Account updated"
        }
      }


  :requestheader X-Cr-User: User name
  :requestheader X-Cr-Token: Auth token

  :statuscode 200: no error


