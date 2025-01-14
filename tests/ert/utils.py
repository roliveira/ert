from __future__ import annotations

import asyncio
import contextlib
import time
from pathlib import Path
from typing import TYPE_CHECKING

import zmq
import zmq.asyncio

from _ert.forward_model_runner.client import ACK_MSG, CONNECT_MSG, DISCONNECT_MSG
from _ert.threading import ErtThread
from ert.scheduler.event import FinishedEvent, StartedEvent

if TYPE_CHECKING:
    from ert.scheduler.driver import Driver


def source_dir() -> Path:
    src = Path("@CMAKE_CURRENT_SOURCE_DIR@/../..")
    if src.is_dir():
        return src.relative_to(Path.cwd())

    # If the file was not correctly configured by cmake, look for the source
    # folder, assuming the build folder is inside the source folder.
    current_path = Path(__file__)
    while current_path != Path("/"):
        if (current_path / ".git").is_dir():
            return current_path
        # This is to find root dir for git worktrees
        elif (current_path / ".git").is_file():
            with open(current_path / ".git", encoding="utf-8") as f:
                for line in f.readlines():
                    if "gitdir:" in line:
                        return current_path

        current_path = current_path.parent
    raise RuntimeError("Cannot find the source folder")


SOURCE_DIR: Path = source_dir()


def wait_until(func, interval=0.5, timeout=30):
    """Waits until func returns True.

    Repeatedly calls 'func' until it returns true.
    Waits 'interval' seconds before each invocation. If 'timeout' is
    reached, will raise the AssertionError.
    """
    t = 0
    while t < timeout:
        time.sleep(interval)
        if func():
            return
        t += interval
    raise AssertionError(
        "Timeout reached in wait_until "
        f"(function {func.__name__}, timeout {timeout:g})."
    )


class MockZMQServer:
    def __init__(self, port, signal=0):
        """Mock ZMQ server for testing
        signal = 0: normal operation
        signal = 1: don't send ACK and don't receive messages
        signal = 2: don't send ACK, but receive messages
        """
        self.port = port
        self.messages = []
        self.value = signal
        self.loop = None
        self.server_task = None
        self.handler_task = None

    def start_event_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self.mock_zmq_server())

    def __enter__(self):
        self.loop = asyncio.new_event_loop()
        self.thread = ErtThread(target=self.start_event_loop)
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self.handler_task and not self.handler_task.done():
            self.loop.call_soon_threadsafe(self.handler_task.cancel)
        self.thread.join()
        self.loop.close()

    async def __aenter__(self):
        self.server_task = asyncio.create_task(self.mock_zmq_server())
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        if not self.server_task.done():
            self.server_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.server_task

    async def mock_zmq_server(self):
        zmq_context = zmq.asyncio.Context()
        self.router_socket = zmq_context.socket(zmq.ROUTER)
        self.router_socket.bind(f"tcp://*:{self.port}")

        self.handler_task = asyncio.create_task(self._handler())
        try:
            await self.handler_task
        finally:
            self.router_socket.close()
            zmq_context.term()

    def signal(self, value):
        self.value = value

    async def _handler(self):
        while True:
            try:
                dealer, __, frame = await self.router_socket.recv_multipart()
                if frame in {CONNECT_MSG, DISCONNECT_MSG} or self.value == 0:
                    await self.router_socket.send_multipart([dealer, b"", ACK_MSG])
                if frame not in {CONNECT_MSG, DISCONNECT_MSG} and self.value != 1:
                    self.messages.append(frame.decode("utf-8"))
            except asyncio.CancelledError:
                break


async def poll(driver: Driver, expected: set[int], *, started=None, finished=None):
    """Poll driver until expected realisations finish

    This function polls the given `driver` until realisations given by
    `expected` finish, either successfully or not, then returns. It is also
    possible to specify `started` and `finished` callbacks, for when a
    realisation starts and finishes, respectively. Blocks until all `expected`
    realisations finish.

    Parameters
    ----------
    driver : Driver
        Driver to poll
    expected : set[int]
        Set of realisation indices that we should wait for
    started : Callable[[int], None]
        Called for each job when it starts. Its associated realisation index is
        passed.
    finished : Callable[[int, int], None]
        Called for each job when it finishes. The first argument is the
        associated realisation index and the second is the returncode of the job
        process.

    """

    poll_task = asyncio.create_task(driver.poll())
    completed = set()
    try:
        while True:
            event = await driver.event_queue.get()
            if isinstance(event, StartedEvent):
                if started:
                    await started(event.iens)
            elif isinstance(event, FinishedEvent):
                if finished is not None:
                    await finished(event.iens, event.returncode)
                completed.add(event.iens)
                if completed == expected:
                    break
    finally:
        poll_task.cancel()
        await driver.finish()
