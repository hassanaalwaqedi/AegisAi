"""
AegisAI - Credential Security Utilities

Utilities for handling sensitive credentials in RTSP URLs
and masking them in logs for security.

Copyright 2024 AegisAI Project
"""

import re
import logging
from typing import Tuple, Optional
from urllib.parse import urlparse, urlunparse

logger = logging.getLogger(__name__)


def mask_rtsp_url(url: str) -> str:
    """
    Mask credentials in RTSP URL for safe logging.
    
    Args:
        url: RTSP URL potentially containing credentials
        
    Returns:
        URL with password replaced by ****
        
    Example:
        >>> mask_rtsp_url("rtsp://admin:secret123@192.168.1.100:554/stream")
        'rtsp://admin:****@192.168.1.100:554/stream'
    """
    if not url:
        return url
    
    # Pattern to match credentials in URL
    # Matches: scheme://user:password@host
    pattern = r'(rtsp://[^:]+:)([^@]+)(@)'
    
    masked = re.sub(pattern, r'\1****\3', url)
    return masked


def parse_rtsp_url(url: str) -> dict:
    """
    Parse RTSP URL into components safely.
    
    Args:
        url: RTSP URL to parse
        
    Returns:
        Dictionary with:
        - scheme: Protocol (rtsp, rtsps)
        - username: Username if present
        - password: Password if present (never log this!)
        - host: IP or hostname
        - port: Port number
        - path: Stream path
    """
    parsed = urlparse(url)
    
    return {
        'scheme': parsed.scheme,
        'username': parsed.username,
        'password': parsed.password,  # Handle with care!
        'host': parsed.hostname,
        'port': parsed.port or 554,
        'path': parsed.path,
    }


def build_rtsp_url(
    host: str,
    path: str = "/stream",
    port: int = 554,
    username: Optional[str] = None,
    password: Optional[str] = None,
    scheme: str = "rtsp"
) -> str:
    """
    Build RTSP URL from components.
    
    Args:
        host: IP or hostname
        path: Stream path
        port: Port number (default 554)
        username: Optional username
        password: Optional password
        scheme: Protocol (rtsp or rtsps)
        
    Returns:
        Complete RTSP URL
    """
    if username and password:
        netloc = f"{username}:{password}@{host}:{port}"
    elif username:
        netloc = f"{username}@{host}:{port}"
    else:
        netloc = f"{host}:{port}"
    
    return urlunparse((scheme, netloc, path, '', '', ''))


class SecureLogger:
    """
    Logging wrapper that automatically masks sensitive data.
    
    Use this instead of direct logger calls when handling RTSP URLs.
    """
    
    def __init__(self, name: str):
        self._logger = logging.getLogger(name)
    
    def _mask_message(self, message: str) -> str:
        """Mask any RTSP URLs in the message."""
        # Pattern to find RTSP URLs
        rtsp_pattern = r'rtsp://[^\s<>"\']+'
        
        def replace_url(match):
            return mask_rtsp_url(match.group(0))
        
        return re.sub(rtsp_pattern, replace_url, str(message))
    
    def info(self, message: str, *args, **kwargs):
        self._logger.info(self._mask_message(message), *args, **kwargs)
    
    def debug(self, message: str, *args, **kwargs):
        self._logger.debug(self._mask_message(message), *args, **kwargs)
    
    def warning(self, message: str, *args, **kwargs):
        self._logger.warning(self._mask_message(message), *args, **kwargs)
    
    def error(self, message: str, *args, **kwargs):
        self._logger.error(self._mask_message(message), *args, **kwargs)
    
    def critical(self, message: str, *args, **kwargs):
        self._logger.critical(self._mask_message(message), *args, **kwargs)


def get_secure_logger(name: str) -> SecureLogger:
    """Get a SecureLogger instance that masks credentials."""
    return SecureLogger(name)
