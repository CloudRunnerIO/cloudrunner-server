from cloudrunner.core.message import *  # noqa


class NodeRegistration(M):
    fields = ['org', 'name']


class Nodes(M):

    dest = ''
    fields = ["nodes"]


class Queued(M):

    dest = ''
    fields = ["task_ids"]


class GetNodes(M):

    dest = ''
    fields = ["org"]


class Fwd(M):

    fields = ['fwd_data']

    # Transport


class InitialMessage(M):
    status = StatusCodes.STARTED
    type = "INITIAL"
    fields = ["type", "session_id", "ts", "org", "user", "seq_no"]


class PipeMessage(M):
    status = StatusCodes.PIPEOUT
    fields = ["type", "session_id", "ts", "seq_no", "org",
              "user", "run_as", "node", "stdout", "stderr"]

    type = "PARTIAL"


class FinishedMessage(M):
    status = StatusCodes.FINISHED
    fields = ["type", "session_id", "ts",
              "user", "org", "result", "env"]

    type = "FINISHED"


class ErrorMessage(M):
    status = StatusCodes.ERROR
    fields = ["type", "session_id", "ts",
              "user", "org", "error"]

    type = "ERROR"


class EndMessage(M):
    status = StatusCodes.FINISHED
    fields = ["type", "session_id"]

    type = "END"
