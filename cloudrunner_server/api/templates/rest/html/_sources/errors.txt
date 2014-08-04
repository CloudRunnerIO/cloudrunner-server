.. _error-handling:

Error handling
==========================

Unless other specified, all action methods(POST, PUT, PATCH, DELETE)
will return the following response::

	{
		"status": "ok"
	}

if the command exited without error, otherwise will return an error code/message as follows::

	{
		"error": "Cannot create user. Missing field: 'username'"
	}
