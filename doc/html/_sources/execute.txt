Execute scripts on remote servers
=================================


.. http:post:: /execute/workflow/(path)?key=(key)&rev=(rev)

  Execute workflow from `path`

  :query string path:    Path to workflow
  :query string key:    optional - ApiKey for identification, or just send the Auth headers
  :query string rev:    optional - Specific version(revision) of the workflow. Default - the latest(HEAD) version

  :form something=value:  Any key=value passed in form data will be available as Environment variables
  :requestheader X-Cr-User: User name (not needed if `key` is passed)
  :requestheader X-Cr-Token: Auth token

  :statuscode 200: no error

  **Example response**:

  .. sourcecode:: http

      HTTP/1.1 200 OK
      Content-Type: application/json; charset=UTF-8

      {
        "success": {
          "msg": "Dispatched",
          "task_uid": "c83146c41aa54d6fba80b55487bb3937",
          "group": 649
        }
      }


.. http:post:: /execute/script/(path)?key=(key)&rev=(rev)

  Execute script from `path`

  :query string path:    Path to workflow
  :query string key:    optional - ApiKey for identification, or just send the Auth headers
  :query string rev:    optional - Specific version(revision) of the workflow. Default - the latest(HEAD) version

  :form targets: (Mandatory) The target selector for nodes to run script on.
  :form something=value:  Any key=value passed in form data will be available as Environment variables

  :requestheader X-Cr-User: User name (not needed if `key` is passed)
  :requestheader X-Cr-Token: Auth token

  **Example response**:

  .. sourcecode:: http

      HTTP/1.1 200 OK
      Content-Type: application/json; charset=UTF-8


      {
        "success": {
          "msg": "Dispatched",
          "task_uid": "c83146c41aa54d6fba80b55487bb3937",
          "group": 649
        }
      }

  :statuscode 200: no error


.. http:post:: /execute/resume/(uuid)/(step)

  Resume script. If the script has multiple steps, the step to be resumed
  can be passed as `step`

  :form something=value:  Any key=value passed in form data will be available as Environment variables

  :query string uuid:    UUID of the script run to be resumed
  :query int step:    The step to resume. Default: 1

  :requestheader X-Cr-User: User name (not needed if `key` is passed)
  :requestheader X-Cr-Token: Auth token

  **Example response**:

  .. sourcecode:: http

      HTTP/1.1 200 OK
      Content-Type: application/json; charset=UTF-8


      {
        "success": {
          "msg": "Dispatched",
          "task_uid": "c83146c41aa54d6fba80b55487bb3937",
          "group": 649
        }
      }

  :statuscode 200: no error


