from datetime import datetime, timezone
from unittest.mock import Mock, ANY
import time

import pytest

from spinach import signals
from spinach.worker import MaxUnfinishedQueue, Workers
from spinach.job import Job


@pytest.fixture
def workers():
    callback = Mock()
    workers = Workers(callback, 2, 'tests')

    yield workers, callback

    workers.stop()


@pytest.fixture
def job():
    task_func = Mock()
    job = Job('foo_task', 'foo_queue', datetime.now(timezone.utc), 10,
              task_args=(1, 2), task_kwargs={'foo': 'bar'})
    job.task_func = task_func

    return job, task_func


def wait_for_queue_empty(workers: Workers, timeout=10):
    for _ in range(timeout * 10):
        if workers._queue.empty():
            return
        time.sleep(0.1)
    raise RuntimeError('Queue did not get empty after {}s'.format(timeout))


def test_max_unfinished_queue():
    queue = MaxUnfinishedQueue(maxsize=2)
    assert queue.empty()

    queue.put(None)
    assert not queue.full()
    assert not queue.empty()

    queue.put(None)
    assert queue.full()

    queue.get()
    assert queue.full()

    queue.task_done()
    assert not queue.full()

    queue.get()
    assert not queue.empty()

    queue.task_done()
    assert queue.empty()


def test_job_execution(workers, job):
    workers, callback = workers
    job, task_func = job
    assert workers.can_accept_job()

    workers.submit_job(job)
    wait_for_queue_empty(workers)

    # Executed function raised no error
    task_func.assert_called_once_with(*job.task_args, **job.task_kwargs)
    callback.assert_called_once_with(job, None)
    assert workers.can_accept_job()

    # Executed function raised an error
    callback.reset_mock()
    task_func.reset_mock()
    error = RuntimeError('Error')
    task_func.side_effect = error

    workers.submit_job(job)
    wait_for_queue_empty(workers)

    task_func.assert_called_once_with(*job.task_args, **job.task_kwargs)
    callback.assert_called_once_with(job, error)


def test_submit_job_shutdown_workers(workers, job):
    workers, callback = workers
    job, task_func = job
    workers.stop()
    with pytest.raises(RuntimeError):
        workers.submit_job(job)


@pytest.mark.parametrize('number', [0, 5])
def test_start_stop_n_workers(number):
    callback = Mock()

    workers = Workers(callback, number, 'tests')
    assert workers._queue.maxsize == number
    assert len(workers._threads) == number
    for thread in workers._threads:
        assert 'tests-worker-' in thread.name

    workers.stop()


def test_worker_signals(job):
    job, task_func = job
    callback = Mock()

    mock_job_started_receiver = Mock(spec={})
    signals.job_started.connect(mock_job_started_receiver)

    mock_job_finished_receiver = Mock(spec={})
    signals.job_finished.connect(mock_job_finished_receiver)

    mock_worker_started_receiver = Mock(spec={})
    signals.worker_started.connect(mock_worker_started_receiver)

    mock_worker_terminated_receiver = Mock(spec={})
    signals.worker_terminated.connect(mock_worker_terminated_receiver)

    ns = 'tests'
    workers = Workers(callback, 1, ns)
    workers.submit_job(job)
    wait_for_queue_empty(workers)
    workers.stop()

    mock_job_started_receiver.assert_called_once_with(ns, job=ANY)
    mock_job_finished_receiver.assert_called_once_with(ns, job=ANY)
    mock_worker_started_receiver.assert_called_once_with(
        ns, worker_name='tests-worker-0'
    )
    mock_worker_terminated_receiver.assert_called_once_with(
        ns, worker_name='tests-worker-0'
    )


def test_can_accept_job(workers, job):
    workers, callback = workers
    assert workers.can_accept_job()

    workers.submit_job(job)
    workers.submit_job(job)
    assert not workers.can_accept_job()

    workers.stop()
    assert not workers.can_accept_job()
