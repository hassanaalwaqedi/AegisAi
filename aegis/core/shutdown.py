"""
AegisAI - Graceful Shutdown Handler

Signal handlers for clean shutdown of the pipeline.

Sprint 2: Production Hardening
"""

import signal
import logging
import threading
from typing import Callable, List, Optional
from functools import partial

# Configure module logger
logger = logging.getLogger(__name__)


class ShutdownHandler:
    """
    Manages graceful shutdown of the application.
    
    Registers cleanup callbacks and handles SIGINT/SIGTERM signals.
    
    Example:
        >>> handler = ShutdownHandler()
        >>> handler.register(video_source.release)
        >>> handler.register(api_server.stop)
        >>> handler.start()
    """
    
    def __init__(self):
        self._callbacks: List[Callable] = []
        self._shutdown_event = threading.Event()
        self._lock = threading.Lock()
        self._started = False
    
    def register(self, callback: Callable, *args, **kwargs) -> None:
        """
        Register a cleanup callback.
        
        Args:
            callback: Function to call on shutdown
            *args: Arguments to pass to callback
            **kwargs: Keyword arguments to pass to callback
        """
        with self._lock:
            if args or kwargs:
                callback = partial(callback, *args, **kwargs)
            self._callbacks.append(callback)
            logger.debug(f"Registered shutdown callback: {callback}")
    
    def start(self) -> None:
        """Start listening for shutdown signals."""
        if self._started:
            return
        
        # Register signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        self._started = True
        logger.info("Shutdown handler started")
    
    def _signal_handler(self, signum: int, frame) -> None:
        """Handle shutdown signal."""
        signal_name = signal.Signals(signum).name
        logger.info(f"Received {signal_name}, initiating graceful shutdown...")
        self.shutdown()
    
    def shutdown(self) -> None:
        """Execute all cleanup callbacks."""
        if self._shutdown_event.is_set():
            return
        
        self._shutdown_event.set()
        
        with self._lock:
            for callback in reversed(self._callbacks):
                try:
                    logger.debug(f"Executing cleanup: {callback}")
                    callback()
                except Exception as e:
                    logger.error(f"Cleanup error: {e}")
        
        logger.info("Graceful shutdown complete")
    
    @property
    def should_shutdown(self) -> bool:
        """Check if shutdown was requested."""
        return self._shutdown_event.is_set()
    
    def wait(self, timeout: Optional[float] = None) -> bool:
        """
        Wait for shutdown signal.
        
        Args:
            timeout: Maximum time to wait (None = forever)
            
        Returns:
            True if shutdown was signaled, False if timeout
        """
        return self._shutdown_event.wait(timeout)


# Global shutdown handler
_handler: Optional[ShutdownHandler] = None


def get_shutdown_handler() -> ShutdownHandler:
    """Get the global shutdown handler."""
    global _handler
    if _handler is None:
        _handler = ShutdownHandler()
    return _handler


def register_cleanup(callback: Callable, *args, **kwargs) -> None:
    """
    Register a cleanup callback with the global handler.
    
    Convenience function for quick registration.
    
    Args:
        callback: Function to call on shutdown
    """
    handler = get_shutdown_handler()
    handler.register(callback, *args, **kwargs)


def is_shutting_down() -> bool:
    """Check if application is shutting down."""
    if _handler is None:
        return False
    return _handler.should_shutdown
