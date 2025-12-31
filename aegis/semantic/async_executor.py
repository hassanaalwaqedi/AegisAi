"""
AegisAI - Async Semantic Executor
Non-Blocking DINO Inference Execution

This module provides asynchronous execution of Grounding DINO inference
to avoid blocking the main detection loop and preserve real-time FPS.

Features:
- ThreadPoolExecutor for background inference
- Non-blocking result polling
- Request queuing with limits
"""

import logging
import threading
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Dict, List, Optional, Tuple, Any
from queue import Queue, Empty

import numpy as np

from aegis.semantic.dino_engine import DinoEngine, SemanticDetection

# Configure module logger
logger = logging.getLogger(__name__)


class SemanticExecutor:
    """
    Async executor for non-blocking DINO inference.
    
    Uses a ThreadPoolExecutor to run DINO inference in background
    threads, allowing the main perception loop to continue without
    waiting for semantic results.
    
    Attributes:
        dino_engine: The Grounding DINO inference engine
        max_workers: Maximum concurrent inference threads
        
    Example:
        >>> executor = SemanticExecutor(dino_engine, max_workers=2)
        >>> executor.submit(track_id=5, image=cropped, prompt="person with bag")
        >>> # Later, poll for results
        >>> results = executor.get_results()  # Non-blocking
    """
    
    def __init__(
        self,
        dino_engine: DinoEngine,
        max_workers: int = 2
    ):
        """
        Initialize the semantic executor.
        
        Args:
            dino_engine: DinoEngine instance for inference
            max_workers: Maximum concurrent inference requests
        """
        self._engine = dino_engine
        self._max_workers = max_workers
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="dino_worker"
        )
        
        # Track pending and completed requests
        self._pending: Dict[int, Future] = {}  # track_id -> Future
        self._results: Dict[int, List[SemanticDetection]] = {}  # track_id -> results
        self._results_lock = threading.Lock()
        
        # Request queue for overflow management
        self._request_queue: Queue = Queue(maxsize=100)
        
        logger.info(f"SemanticExecutor initialized with {max_workers} workers")
    
    def submit(
        self,
        track_id: int,
        image: np.ndarray,
        prompt: str
    ) -> Optional[Future]:
        """
        Submit an async DINO inference request.
        
        Args:
            track_id: ID of the track to analyze
            image: Cropped image region
            prompt: Text prompt for semantic matching
            
        Returns:
            Future object if submitted, None if queue full
        """
        # Check if we already have a pending request for this track
        if track_id in self._pending and not self._pending[track_id].done():
            logger.debug(f"Track {track_id} already has pending request")
            return None
        
        # Submit to thread pool
        try:
            future = self._executor.submit(
                self._run_inference,
                track_id,
                image,
                prompt
            )
            self._pending[track_id] = future
            
            logger.debug(f"Submitted semantic request for track {track_id}: '{prompt[:30]}...'")
            return future
            
        except Exception as e:
            logger.error(f"Failed to submit semantic request: {e}")
            return None
    
    def _run_inference(
        self,
        track_id: int,
        image: np.ndarray,
        prompt: str
    ) -> Tuple[int, List[SemanticDetection]]:
        """
        Execute DINO inference (runs in thread pool).
        
        Args:
            track_id: Track identifier
            image: Input image
            prompt: Text prompt
            
        Returns:
            Tuple of (track_id, detections)
        """
        try:
            detections = self._engine.infer(image, prompt)
            
            # Store results
            with self._results_lock:
                self._results[track_id] = detections
            
            logger.debug(
                f"DINO completed for track {track_id}: "
                f"{len(detections)} detections"
            )
            
            return track_id, detections
            
        except Exception as e:
            logger.error(f"DINO inference failed for track {track_id}: {e}")
            return track_id, []
    
    def get_results(self) -> Dict[int, List[SemanticDetection]]:
        """
        Get completed results (non-blocking).
        
        Returns:
            Dict mapping track_id to semantic detections.
            Only includes results from completed inferences.
        """
        # Collect completed futures
        completed_tracks = []
        for track_id, future in list(self._pending.items()):
            if future.done():
                completed_tracks.append(track_id)
                # Results already stored in _results by _run_inference
        
        # Clean up completed futures
        for track_id in completed_tracks:
            del self._pending[track_id]
        
        # Return and clear results
        with self._results_lock:
            results = self._results.copy()
            self._results.clear()
        
        return results
    
    def get_pending_count(self) -> int:
        """Get number of pending inference requests."""
        return len(self._pending)
    
    def wait_for_completion(self, timeout: Optional[float] = None) -> bool:
        """
        Wait for all pending requests to complete.
        
        Args:
            timeout: Maximum seconds to wait (None = wait forever)
            
        Returns:
            True if all completed, False if timeout
        """
        for track_id, future in list(self._pending.items()):
            try:
                future.result(timeout=timeout)
            except Exception as e:
                logger.error(f"Error waiting for track {track_id}: {e}")
        
        return len(self._pending) == 0
    
    def cancel_all(self) -> int:
        """
        Cancel all pending requests.
        
        Returns:
            Number of requests cancelled
        """
        cancelled = 0
        for track_id, future in list(self._pending.items()):
            if future.cancel():
                cancelled += 1
        
        self._pending.clear()
        logger.info(f"Cancelled {cancelled} pending semantic requests")
        return cancelled
    
    def shutdown(self, wait: bool = True) -> None:
        """
        Shutdown the executor.
        
        Args:
            wait: Whether to wait for pending tasks to complete
        """
        logger.info("Shutting down SemanticExecutor...")
        self._executor.shutdown(wait=wait)
        self._pending.clear()
        with self._results_lock:
            self._results.clear()
        logger.info("SemanticExecutor shutdown complete")
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.shutdown(wait=True)
        return False
    
    def __repr__(self) -> str:
        return (
            f"SemanticExecutor(workers={self._max_workers}, "
            f"pending={len(self._pending)})"
        )
