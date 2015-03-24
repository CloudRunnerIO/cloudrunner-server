Scheduled jobs module
=====================


.. http:get:: /scheduler/jobs/

  Load scheduled jobs list

  **Example response**:

  .. sourcecode:: http

      HTTP/1.1 200 OK
      Content-Type: application/json; charset=UTF-8

      {
        "jobs": [
          {
            "name": "Job1",
            "script": {
              "path": "/Path/To/Script",
              "rev": "6",
              "name": "details"
            },
            "created_at": "2015-02-10 01:22:02",
            "enabled": true,
            "private": false,
            "params": {},
            "owner": "username",
            "exec_period": "5 * * * * "
          }
        ],
        "quota": {"allowed": 10}
      }

  :requestheader X-Cr-User: User name
  :requestheader X-Cr-Token: Auth token

  :statuscode 200: no error



.. http:post:: /scheduler/jobs/

  Create new scheduled job

  :form name: Job name
  :form script: Path to script
  :form period: Period to execute (Eg. 0 * * * *  - execute on every hour)

  :form version: (optional) Specific version of the script. Defaults to HEAD
  :form private: (optional) Set the job as private - only visible to the owner. Defaults to 0(false)
  :form enabled: (optional) Enable/disable the job. Defaults to 1(true)

  :requestheader X-Cr-User: User name
  :requestheader X-Cr-Token: Auth token

  **Example request**:

   .. sourcecode:: http

      PUT /billing/account HTTP/1.1
      Host: api.cloudrunner.io
      Accept: application/json
      Content-Type:application/x-www-form-urlencoded; charset=UTF-8

      name=test&script=/Demo/details&private=false&enabled=true&period=5 * * * *

  **Example response**:

  .. sourcecode:: http

      HTTP/1.1 200 OK
      Content-Type: application/json; charset=UTF-8

      {
        "success": {
          "status": "ok"
        }
      }

  :statuscode 200: no error


.. http:delete:: /scheduler/jobs/(name)

  Delete a scheduled job

  :query name: The job name

  **Example response**:

  .. sourcecode:: http

      HTTP/1.1 200 OK
      Content-Type: application/json; charset=UTF-8

      {
        "success": {
          "status": "ok"
        }
      }

  :statuscode 200: no error
