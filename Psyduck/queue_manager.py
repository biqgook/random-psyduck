import asyncio
import logging
from typing import Callable, Any
from datetime import datetime

logger = logging.getLogger('Psyduck')


class CommandQueue:
    def __init__(self, delay_seconds: int = 5):
        """
        Initialize the command queue with delay between executions
        
        Args:
            delay_seconds: Seconds to wait between command executions
        """
        self.delay_seconds = delay_seconds
        self.queue = asyncio.Queue()
        self.is_processing = False
        self.lock = asyncio.Lock()
    
    async def add_to_queue(self, callback: Callable, *args, **kwargs):
        """
        Add a command to the queue
        
        Args:
            callback: Async function to call
            *args, **kwargs: Arguments to pass to the callback
        """
        await self.queue.put((callback, args, kwargs, datetime.now()))
        logger.info(f"Added command to queue. Queue size: {self.queue.qsize()}")
        
        # Start processing if not already running
        if not self.is_processing:
            asyncio.create_task(self._process_queue())
    
    async def _process_queue(self):
        """Process commands from the queue with delays"""
        async with self.lock:
            if self.is_processing:
                return
            self.is_processing = True
        
        try:
            while not self.queue.empty():
                callback, args, kwargs, timestamp = await self.queue.get()
                
                try:
                    # Execute the command
                    await callback(*args, **kwargs)
                    logger.info(f"Executed command from queue. Remaining: {self.queue.qsize()}")
                except Exception as e:
                    logger.exception(f"Error executing queued command: {e}")
                finally:
                    self.queue.task_done()
                
                # Wait before processing next command (if there is one)
                if not self.queue.empty():
                    logger.info(f"Waiting {self.delay_seconds} seconds before next command...")
                    await asyncio.sleep(self.delay_seconds)
        
        finally:
            async with self.lock:
                self.is_processing = False
    
    def get_queue_position(self) -> int:
        """Get current queue size"""
        return self.queue.qsize()
