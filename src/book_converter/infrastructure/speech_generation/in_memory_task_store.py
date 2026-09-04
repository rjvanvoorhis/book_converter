import dataclasses
import threading
import typing
import uuid

TaskStatus = typing.Literal["pending", "running", "completed", "failed", "cancelled"]

_TERMINAL_STATUSES: frozenset[TaskStatus] = frozenset(
    {"completed", "failed", "cancelled"}
)


@dataclasses.dataclass
class TaskState:
    id: str
    status: TaskStatus
    message: str
    result: dict | None = None
    error: str | None = None


class InMemoryTaskStore:
    """Tracks long-running audiobook generation runs in memory so an HTTP
    client can poll for progress instead of holding a request open for the
    whole run. Single-process only: state is lost on server restart, which is
    fine for this tool's local, one-worker deployment.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tasks: dict[str, TaskState] = {}
        self._blobs: dict[str, tuple[bytes, str]] = {}
        self._cancel_requested: set[str] = set()

    def create(self) -> str:
        task_id = str(uuid.uuid4())
        with self._lock:
            self._tasks[task_id] = TaskState(
                id=task_id, status="pending", message="Queued"
            )
        return task_id

    def get(self, task_id: str) -> TaskState | None:
        with self._lock:
            return self._tasks.get(task_id)

    def report_progress(self, task_id: str, message: str) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is not None:
                task.status = "running"
                task.message = message

    def complete(self, task_id: str, result: dict) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is not None:
                task.status = "completed"
                task.message = "Done"
                task.result = result

    def fail(self, task_id: str, error: str) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is not None:
                task.status = "failed"
                task.message = "Failed"
                task.error = error

    def request_cancellation(self, task_id: str) -> bool:
        """Ask a running task to stop. Cooperative: the task's own code has
        to check `is_cancellation_requested` at its own checkpoints and
        unwind itself - nothing here can forcibly interrupt a thread.
        Returns False if the task doesn't exist or has already finished."""
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None or task.status in _TERMINAL_STATUSES:
                return False
            self._cancel_requested.add(task_id)
            return True

    def is_cancellation_requested(self, task_id: str) -> bool:
        with self._lock:
            return task_id in self._cancel_requested

    def mark_cancelled(self, task_id: str) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is not None:
                task.status = "cancelled"
                task.message = "Cancelled"
            self._cancel_requested.discard(task_id)

    def store_blob(self, task_id: str, data: bytes, content_type: str) -> None:
        """Stash a binary result (e.g. sample audio) a task produced, so a
        client can fetch it once the task's JSON status shows it's ready."""
        with self._lock:
            self._blobs[task_id] = (data, content_type)

    def get_blob(self, task_id: str) -> tuple[bytes, str] | None:
        with self._lock:
            return self._blobs.get(task_id)
