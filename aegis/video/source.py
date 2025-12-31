"""
AegisAI - Smart City Risk Intelligence System
Video Source Handler Module

This module provides unified video input handling for files and camera streams.
Designed for robust, production-grade video processing with automatic resource management.

Features:
- Unified interface for files and cameras
- Automatic metadata extraction
- Generator-based frame iteration
- Context manager support for safe cleanup
"""

import logging
from typing import Iterator, Optional, Tuple, Union
from pathlib import Path

import cv2
import numpy as np

from config import VideoConfig, AegisConfig

# Configure module logger
logger = logging.getLogger(__name__)


class VideoSourceError(Exception):
    """Custom exception for video source errors."""
    pass


class VideoSource:
    """
    Unified video source handler for files and camera streams.
    
    Provides a consistent interface for accessing video frames
    regardless of the input source type. Supports both file paths
    and camera device indices.
    
    Attributes:
        source: Original source path or camera index
        is_camera: Whether the source is a camera stream
        frame_count: Total frames (0 for cameras)
        fps: Frames per second
        width: Frame width in pixels
        height: Frame height in pixels
        
    Example:
        >>> with VideoSource("video.mp4") as source:
        ...     for frame in source:
        ...         process(frame)
        
        >>> source = VideoSource(0)  # Camera index
        >>> source.open()
        >>> for frame in source:
        ...     if cv2.waitKey(1) == ord('q'):
        ...         break
        >>> source.release()
    """
    
    def __init__(
        self,
        source: Union[str, int, Path],
        config: Optional[AegisConfig] = None,
        video_config: Optional[VideoConfig] = None
    ):
        """
        Initialize the video source handler.
        
        Args:
            source: Video file path or camera device index
            config: Full AegisConfig instance (preferred)
            video_config: VideoConfig instance (alternative)
            
        Raises:
            VideoSourceError: If source is invalid
        """
        if config is not None:
            self._config = config.video
        elif video_config is not None:
            self._config = video_config
        else:
            self._config = VideoConfig()
        
        # Determine source type
        if isinstance(source, int):
            self._source = source
            self._is_camera = True
        elif isinstance(source, (str, Path)):
            self._source = str(source)
            self._is_camera = False
            
            # Validate file exists for file sources
            if not Path(self._source).exists():
                raise VideoSourceError(f"Video file not found: {self._source}")
        else:
            raise VideoSourceError(
                f"Invalid source type: {type(source)}. "
                "Expected str, Path, or int (camera index)"
            )
        
        self._capture: Optional[cv2.VideoCapture] = None
        self._frame_count = 0
        self._current_frame = 0
        self._fps = 0.0
        self._width = 0
        self._height = 0
        
        logger.info(f"VideoSource created for: {self._source}")
    
    @property
    def source(self) -> Union[str, int]:
        """Get the original source path or camera index."""
        return self._source
    
    @property
    def is_camera(self) -> bool:
        """Check if source is a camera stream."""
        return self._is_camera
    
    @property
    def is_open(self) -> bool:
        """Check if the video source is currently open."""
        return self._capture is not None and self._capture.isOpened()
    
    @property
    def frame_count(self) -> int:
        """Get total frame count (0 for cameras)."""
        return self._frame_count
    
    @property
    def current_frame(self) -> int:
        """Get current frame position."""
        return self._current_frame
    
    @property
    def fps(self) -> float:
        """Get frames per second."""
        return self._fps
    
    @property
    def width(self) -> int:
        """Get frame width in pixels."""
        return self._width
    
    @property
    def height(self) -> int:
        """Get frame height in pixels."""
        return self._height
    
    @property
    def resolution(self) -> Tuple[int, int]:
        """Get frame resolution as (width, height)."""
        return (self._width, self._height)
    
    def open(self) -> 'VideoSource':
        """
        Open the video source for reading.
        
        Returns:
            Self for method chaining
            
        Raises:
            VideoSourceError: If source cannot be opened
        """
        if self._capture is not None:
            self.release()
        
        self._capture = cv2.VideoCapture(self._source)
        
        if not self._capture.isOpened():
            raise VideoSourceError(
                f"Failed to open video source: {self._source}"
            )
        
        # Extract metadata
        self._fps = self._capture.get(cv2.CAP_PROP_FPS)
        self._width = int(self._capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        self._height = int(self._capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        if not self._is_camera:
            self._frame_count = int(
                self._capture.get(cv2.CAP_PROP_FRAME_COUNT)
            )
        else:
            self._frame_count = 0
        
        self._current_frame = 0
        
        logger.info(
            f"Video source opened: {self._width}x{self._height} @ {self._fps:.2f} FPS, "
            f"frames={self._frame_count if self._frame_count > 0 else 'live'}"
        )
        
        return self
    
    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        """
        Read a single frame from the video source.
        
        Returns:
            Tuple of (success, frame) where frame is None on failure
        """
        if not self.is_open:
            return False, None
        
        ret, frame = self._capture.read()
        
        if ret:
            self._current_frame += 1
            
            # Apply resize if configured
            if (self._config.resize_width is not None and 
                self._config.resize_height is not None):
                frame = cv2.resize(
                    frame,
                    (self._config.resize_width, self._config.resize_height)
                )
        
        return ret, frame
    
    def seek(self, frame_number: int) -> bool:
        """
        Seek to a specific frame (file sources only).
        
        Args:
            frame_number: Target frame number (0-indexed)
            
        Returns:
            True if seek was successful
        """
        if self._is_camera:
            logger.warning("Seek not supported for camera sources")
            return False
        
        if not self.is_open:
            return False
        
        if frame_number < 0 or frame_number >= self._frame_count:
            return False
        
        self._capture.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
        self._current_frame = frame_number
        return True
    
    def release(self) -> None:
        """Release the video source and free resources."""
        if self._capture is not None:
            self._capture.release()
            self._capture = None
            logger.info("Video source released")
    
    def __iter__(self) -> Iterator[np.ndarray]:
        """
        Iterate over frames in the video source.
        
        Yields:
            Video frames as numpy arrays (BGR format)
        """
        if not self.is_open:
            self.open()
        
        while True:
            ret, frame = self.read()
            
            if not ret:
                break
            
            yield frame
    
    def __enter__(self) -> 'VideoSource':
        """Context manager entry - opens the source."""
        return self.open()
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - releases resources."""
        self.release()
    
    def __len__(self) -> int:
        """Get total frame count (0 for cameras)."""
        return self._frame_count
    
    def __repr__(self) -> str:
        status = "open" if self.is_open else "closed"
        return (
            f"VideoSource(source={self._source}, status={status}, "
            f"resolution={self._width}x{self._height}, fps={self._fps:.2f})"
        )
