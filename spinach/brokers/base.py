from abc import ABC, abstractmethod
from datetime import datetime
from logging import getLogger
import threading
from typing import Optional

from ..job import Job
from ..const import WAIT_FOR_EVENT_MAX_SECONDS

logger = getLogger('spinach.broker')


class Broker(ABC):

    def __init__(self):
        self._something_happened = threading.Event()
        self._namespace = None

    def wait_for_event(self):
        next_future_job_delta = self.next_future_job_delta
        if next_future_job_delta is None:
            timeout = WAIT_FOR_EVENT_MAX_SECONDS
        else:
            timeout = min(next_future_job_delta, WAIT_FOR_EVENT_MAX_SECONDS)
        if self._something_happened.wait(timeout=timeout):
            self._something_happened.clear()

    def start(self):
        """Start the broker.

        Only needed by arbiter.
        """

    def stop(self):
        """Stop the broker.

        Only needed by arbiter.
        """
        self._something_happened.set()

    @property
    def namespace(self) -> str:
        if not self._namespace:
            raise RuntimeError('Namespace must be set before using the broker')
        return self._namespace

    @namespace.setter
    def namespace(self, value: str):
        if self._namespace:
            raise RuntimeError('The namespace can only be set once')
        self._namespace = value

    def _to_namespaced(self, value: str) -> str:
        return '{}/{}'.format(self.namespace, value)

    @abstractmethod
    def enqueue_job(self, job: Job):
        """Add a job to a queue."""

    def job_finished(self, job: Job):
        """Notification that a job has been ran (successfully or not)."""
        self._something_happened.set()

    @abstractmethod
    def get_job_from_queue(self, queue: str):
        """Get a job from a queue."""

    @abstractmethod
    def move_future_jobs(self) -> int:
        """Move ready jobs from the future queue to their normal queues.

        :returns the number of jobs moved
        """

    @abstractmethod
    def _get_next_future_job(self)-> Optional[Job]:
        """Get the next future job."""

    @property
    def next_future_job_delta(self) -> Optional[float]:
        """Give the amount of seconds before the next future job is due."""
        job = self._get_next_future_job()
        if not job:
            return None
        return (job.at - datetime.utcnow()).total_seconds()