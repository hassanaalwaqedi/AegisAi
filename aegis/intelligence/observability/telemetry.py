"""
AI-Observable Telemetry Pipeline
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Callable
import time
import functools


class TelemetryType(Enum):
    TRACE = "trace"
    METRIC = "metric"
    LOG = "log"


class SpanStatus(Enum):
    OK = "ok"
    ERROR = "error"
    TIMEOUT = "timeout"


@dataclass
class Span:
    """Distributed tracing span"""
    name: str
    trace_id: str
    span_id: str
    parent_id: Optional[str] = None
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    status: SpanStatus = SpanStatus.OK
    attributes: dict = field(default_factory=dict)
    events: list[dict] = field(default_factory=list)
    
    @property
    def duration_ms(self) -> float:
        if self.end_time is None:
            return (time.time() - self.start_time) * 1000
        return (self.end_time - self.start_time) * 1000
    
    def add_event(self, name: str, attributes: dict = None):
        self.events.append({
            "name": name,
            "timestamp": time.time(),
            "attributes": attributes or {},
        })
    
    def set_error(self, error: Exception):
        self.status = SpanStatus.ERROR
        self.attributes["error.type"] = type(error).__name__
        self.attributes["error.message"] = str(error)
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_id": self.parent_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": self.duration_ms,
            "status": self.status.value,
            "attributes": self.attributes,
            "events": self.events,
        }


@dataclass
class Metric:
    """Observable metric"""
    name: str
    value: float
    timestamp: float = field(default_factory=time.time)
    labels: dict = field(default_factory=dict)
    unit: str = ""
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "value": self.value,
            "timestamp": self.timestamp,
            "labels": self.labels,
            "unit": self.unit,
        }


class TelemetryCollector:
    """Collects and manages AI-observable telemetry"""
    
    def __init__(self):
        self._spans: list[Span] = []
        self._metrics: list[Metric] = []
        self._trace_counter = 0
    
    def _generate_id(self, prefix: str = "span") -> str:
        self._trace_counter += 1
        return f"{prefix}_{int(time.time() * 1000)}_{self._trace_counter}"
    
    def start_span(self, name: str, parent_id: str = None) -> Span:
        """Start a new trace span"""
        span = Span(
            name=name,
            trace_id=self._generate_id("trace"),
            span_id=self._generate_id("span"),
            parent_id=parent_id,
        )
        self._spans.append(span)
        return span
    
    def end_span(self, span: Span, status: SpanStatus = SpanStatus.OK):
        """End a trace span"""
        span.end_time = time.time()
        span.status = status
    
    def record_metric(self, name: str, value: float, labels: dict = None, unit: str = ""):
        """Record a metric value"""
        metric = Metric(name=name, value=value, labels=labels or {}, unit=unit)
        self._metrics.append(metric)
    
    def get_recent_spans(self, limit: int = 100) -> list[dict]:
        """Get recent spans"""
        return [s.to_dict() for s in self._spans[-limit:]]
    
    def get_recent_metrics(self, limit: int = 100) -> list[dict]:
        """Get recent metrics"""
        return [m.to_dict() for m in self._metrics[-limit:]]


def trace(collector: TelemetryCollector, name: str = None):
    """Decorator to trace function execution"""
    def decorator(func: Callable):
        span_name = name or func.__name__
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            span = collector.start_span(span_name)
            try:
                result = func(*args, **kwargs)
                collector.end_span(span, SpanStatus.OK)
                return result
            except Exception as e:
                span.set_error(e)
                collector.end_span(span, SpanStatus.ERROR)
                raise
        
        return wrapper
    return decorator
