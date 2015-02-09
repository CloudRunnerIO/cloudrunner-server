Authentication module
=====================


.. http:post:: /auth/login/

  Login and get authentication token

  **Example response**:

  .. sourcecode:: http

      HTTP/1.1 200 OK
      Content-Type: application/json; charset=UTF-8

      {
        "login": {
          "token": "nFLfLCqv2O61_Wh-flEcTY~CX1JBjclqrqfbD9zGQbAgt56RBrc-tt_q4NcEWgYu",
          "expire": "2016-02-11 00:33:01",
          "user": "Username",
          "org": "Organization"
        }
      }

  :form username:    User name
  :form password:    User password
  :form expire:      Expire for the token in minutes(Default=1440)

  :requestheader X-Cr-User: User name
  :requestheader X-Cr-Token: Auth token

  :statuscode 200: no error



.. http:get:: /auth/logout/

  Logout and destroy session

  :requestheader X-Cr-User: User name
  :requestheader X-Cr-Token: Auth token

  :statuscode 200: no error

