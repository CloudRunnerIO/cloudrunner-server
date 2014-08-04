.. _scheduler:

Scheduler Controller
====================

Provides support for schedulere jobs(using Cron)

.. seealso::

	* `Cron <http://en.wikipedia.org/wiki/Cron>`_

.. note::

	* This controller requires authentication headers. See how to add headers in request: :ref:`secure-headers`

Scheduler
----------

List existing scheduler jobs
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

**[GET] /rest/scheduler/jobs**

	Request::

		curl -H "Cr-User=user" -H "Cr-Token=token" \
			https://rest-api-server/scheduler/jobs

	Response::

		{"jobs":
			[
				{
					"enabled": true,
					"user": "cloudr",
					"name": "job1",
					"period": "0,15,30,45 * * * *"
				},
				{
					"enabled": true,
					"user": "cloudr",
					"name": "job2",
					"period": "@hourly"
				},
				{
					"enabled": true,
					"user": "cloudr",
					"name": "job3",
					"period": "@hourly"
				}
			]
		}

Display scheduler jobs details
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

**[GET] /rest/scheduler/jobs/<name>**

	**Params**::

		<name>
			Job name

	Request::

		curl -H "Cr-User=user" -H "Cr-Token=token" \
			https://rest-api-server/scheduler/jobs/job1

	Response::

		{
			"job":
			{
				"content": "#! switch [*]\\n hostname",
				"enabled": True,
				"job_id": "ef3c873acd5845b69d0418ae60667c46",
				"name": "job1",
				"owner": "cloudr",
				"period": "0,15,30,45 * * * *"
			}
		}

Create new scheduler job
^^^^^^^^^^^^^^^^^^^^^^^^

**[POST] /rest/scheduler/jobs**

	Request::

		curl -X POST -H "Cr-User=user" -H "Cr-Token=token" \
			https://rest-api-server/scheduler/jobs \
			-d name=JOB1&period="0 * * * *"&content="Job content here..."

	Response::

		{
			"status": "ok"
		}

Update a scheduler job
^^^^^^^^^^^^^^^^^^^^^^

**[PUT] /rest/scheduler/jobs**

or

**[PATCH] /rest/scheduler/jobs**

	**POST data**

		<name>

			Name of job

		<?content>

			*Optional*. Content of the job to be executed. If not passed will not be modified.

		<?period>

			*Optional*. Period for execution, see `Cron <http://en.wikipedia.org/wiki/Cron>`_ for details how to define periods.
			If not passed will not be modified.

	Request::

		curl -X POST -H "Cr-User=user" -H "Cr-Token=token" \
			https://rest-api-server/scheduler/jobs \
			-d name=JOB1&period="1 * * * *"

	Response::

		{
			"status": "ok"
		}

Delete a scheduler job
^^^^^^^^^^^^^^^^^^^^^^

**[DELETE] /rest/scheduler/jobs/<job_name>**

	**Params**

		<job_name>

			Name of job

	Request::

		curl -X DELETE -H "Cr-User=user" -H "Cr-Token=token" \
			https://rest-api-server/scheduler/jobs/JOB1

	Response::

		{
			"status": "ok"
		}

Error handling
^^^^^^^^^^^^^^

.. seealso:: :ref:`error-handling`