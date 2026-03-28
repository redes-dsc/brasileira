import asyncio
import logging
from dataclasses import dataclass
from typing import Callable, Awaitable

logger = logging.getLogger(__name__)


@dataclass
class SourceAssignment:
    source_id: str
    source_type: str
    payload: dict


class WorkerPool:
    def __init__(self, workers: int = 30) -> None:
        self.workers = workers
        self.queue: asyncio.Queue[SourceAssignment] = asyncio.Queue()
        self._tasks: list[asyncio.Task] = []
        self._shutdown = False

    async def start(self, handler: Callable[[SourceAssignment], Awaitable[None]]) -> None:
        """Starts the worker pool with the given async handler."""
        for i in range(self.workers):
            task = asyncio.create_task(self.worker_loop(handler, i))
            self._tasks.append(task)
        logger.info(f"WorkerPool started with {self.workers} workers")

    async def submit(self, assignment: SourceAssignment) -> None:
        if self._shutdown:
            raise RuntimeError("WorkerPool is shutting down")
        await self.queue.put(assignment)

    async def stop(self) -> None:
        """Gracefully stops the worker pool."""
        self._shutdown = True
        await self.queue.join()  # Wait for queue to empty
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        logger.info("WorkerPool stopped")

    async def worker_loop(self, handler: Callable[[SourceAssignment], Awaitable[None]], worker_id: int):
        while not self._shutdown:
            try:
                # Use a timeout to allow checking shutdown flag periodically if queue is empty
                try:
                    item = await asyncio.wait_for(self.queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

                try:
                    await handler(item)
                except Exception as e:
                    logger.error(f"Worker {worker_id} failed processing {item}: {e}", exc_info=True)
                finally:
                    self.queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.critical(f"Worker {worker_id} crashed loop: {e}", exc_info=True)
                await asyncio.sleep(1)  # Prevent tight loop on crash
