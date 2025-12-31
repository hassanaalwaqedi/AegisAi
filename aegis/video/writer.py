"""
AegisAI - Smart City Risk Intelligence System
Video Writer Module

This module provides production-grade video output writing with
configurable codec, quality, and automatic FPS matching.

Features:
- Multiple codec support
- Automatic FPS and resolution handling
- Context manager for safe resource cleanup
- Configurable output quality
"""

import logging
from typing import Optional, Tuple
from pathlib import Path

import cv2
import numpy as np

from config import VideoConfig, AegisConfig

# Configure module logger
logger = logging.getLogger(__name__)


class VideoWriterError(Exception):
    """Custom exception for video writer errors."""
    pass


class VideoWriter:
    """
    Production-grade video output writer.
    
    Provides reliable video file output with automatic codec
    selection and resource management.
    
    Attributes:
        output_path: Path to the output video file
        fps: Output frames per second
        resolution: Output resolution (width, height)
        
    Example:
        >>> with VideoWriter("output.mp4", fps=30, resolution=(1920, 1080)) as writer:
        ...     for frame in frames:
        ...         writer.write(frame)
        
        >>> writer = VideoWriter("output.mp4")
        >>> writer.open(fps=30, resolution=(1920, 1080))
        >>> writer.write(frame)
        >>> writer.release()
    """
    
    def __init__(
        self,
        output_path: str,
        fps: Optional[float] = None,
        resolution: Optional[Tuple[int, int]] = None,
        config: Optional[AegisConfig] = None,
        video_config: Optional[VideoConfig] = None
    ):
        """
        Initialize the video writer.
        
        Args:
            output_path: Path for the output video file
            fps: Frames per second (can be set later in open())
            resolution: Output resolution as (width, height)
            config: Full AegisConfig instance (preferred)
            video_config: VideoConfig instance (alternative)
        """
        if config is not None:
            self._config = config.video
        elif video_config is not None:
            self._config = video_config
        else:
            self._config = VideoConfig()
        
        self._output_path = str(output_path)
        self._fps = fps
        self._resolution = resolution
        self._writer: Optional[cv2.VideoWriter] = None
        self._frame_count = 0
        
        # Ensure output directory exists
        output_dir = Path(self._output_path).parent
        output_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"VideoWriter created for: {self._output_path}")
    
    @property
    def output_path(self) -> str:
        """Get the output file path."""
        return self._output_path
    
    @property
    def fps(self) -> Optional[float]:
        """Get the output FPS."""
        return self._fps
    
    @property
    def resolution(self) -> Optional[Tuple[int, int]]:
        """Get the output resolution."""
        return self._resolution
    
    @property
    def frame_count(self) -> int:
        """Get the number of frames written."""
        return self._frame_count
    
    @property
    def is_open(self) -> bool:
        """Check if the writer is currently open."""
        return self._writer is not None and self._writer.isOpened()
    
    def open(
        self,
        fps: Optional[float] = None,
        resolution: Optional[Tuple[int, int]] = None
    ) -> 'VideoWriter':
        """
        Open the video writer for writing.
        
        Args:
            fps: Frames per second (overrides constructor value)
            resolution: Output resolution as (width, height)
            
        Returns:
            Self for method chaining
            
        Raises:
            VideoWriterError: If required parameters are missing
        """
        # Use provided values or fall back to stored ones
        self._fps = fps or self._fps or self._config.output_fps
        self._resolution = resolution or self._resolution
        
        if self._fps is None:
            raise VideoWriterError(
                "FPS must be specified either in constructor or open()"
            )
        
        if self._resolution is None:
            raise VideoWriterError(
                "Resolution must be specified either in constructor or open()"
            )
        
        # Get codec fourcc
        fourcc = cv2.VideoWriter_fourcc(*self._config.output_codec)
        
        # Create writer
        self._writer = cv2.VideoWriter(
            self._output_path,
            fourcc,
            self._fps,
            self._resolution
        )
        
        if not self._writer.isOpened():
            raise VideoWriterError(
                f"Failed to open video writer: {self._output_path}"
            )
        
        self._frame_count = 0
        
        logger.info(
            f"Video writer opened: {self._resolution[0]}x{self._resolution[1]} "
            f"@ {self._fps:.2f} FPS, codec={self._config.output_codec}"
        )
        
        return self
    
    def write(self, frame: np.ndarray) -> bool:
        """
        Write a single frame to the output video.
        
        Args:
            frame: Video frame as numpy array (BGR format)
            
        Returns:
            True if write was successful
        """
        if not self.is_open:
            logger.warning("Attempting to write to closed VideoWriter")
            return False
        
        # Ensure frame matches expected resolution
        h, w = frame.shape[:2]
        if (w, h) != self._resolution:
            frame = cv2.resize(frame, self._resolution)
        
        self._writer.write(frame)
        self._frame_count += 1
        
        return True
    
    def release(self) -> None:
        """Release the video writer and finalize the output file."""
        if self._writer is not None:
            self._writer.release()
            self._writer = None
            
            logger.info(
                f"Video writer released: {self._frame_count} frames written "
                f"to {self._output_path}"
            )
    
    def __enter__(self) -> 'VideoWriter':
        """Context manager entry - opens the writer if configured."""
        if self._fps is not None and self._resolution is not None:
            return self.open()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - releases resources."""
        self.release()
    
    def __repr__(self) -> str:
        status = "open" if self.is_open else "closed"
        return (
            f"VideoWriter(path={self._output_path}, status={status}, "
            f"resolution={self._resolution}, fps={self._fps}, "
            f"frames={self._frame_count})"
        )
