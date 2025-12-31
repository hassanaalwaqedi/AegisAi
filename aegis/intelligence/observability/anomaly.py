"""
Anomaly Detection - Database Connected
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional
from sqlalchemy.orm import Session
import statistics

from aegis.database import AnomalyRepository


class AnomalyType(Enum):
    USER_FLOW = "user_flow"
    API_LATENCY = "api_latency"
    ERROR_RATE = "error_rate"
    TRAFFIC_SPIKE = "traffic_spike"


class AnomalySeverity(Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AnomalyDetector:
    """Detects and persists anomalies to database."""
    
    def __init__(self, db: Session = None, window_size: int = 100, z_threshold: float = 2.5):
        self._db = db
        self._window_size = window_size
        self._z_threshold = z_threshold
        self._history: dict[str, list[float]] = {}
    
    def _get_history(self, metric: str) -> list[float]:
        if metric not in self._history:
            self._history[metric] = []
        return self._history[metric]
    
    def _add_to_history(self, metric: str, value: float):
        history = self._get_history(metric)
        history.append(value)
        if len(history) > self._window_size:
            history.pop(0)
    
    def _calculate_z_score(self, value: float, history: list[float]) -> float:
        if len(history) < 3:
            return 0.0
        mean = statistics.mean(history)
        stdev = statistics.stdev(history)
        if stdev == 0:
            return 0.0
        return (value - mean) / stdev
    
    def check_latency(self, endpoint: str, latency_ms: float, db: Session = None) -> Optional[dict]:
        """Check for API latency anomalies and persist if detected."""
        metric = f"latency:{endpoint}"
        history = self._get_history(metric)
        
        anomaly = None
        if len(history) >= 10:
            z_score = self._calculate_z_score(latency_ms, history)
            if abs(z_score) > self._z_threshold:
                mean = statistics.mean(history)
                severity = AnomalySeverity.CRITICAL if z_score > 4 else AnomalySeverity.WARNING
                
                # Persist to database
                if db or self._db:
                    repo = AnomalyRepository(db or self._db)
                    db_anomaly = repo.save(
                        anomaly_type=AnomalyType.API_LATENCY.value,
                        severity=severity.value,
                        metric_name=endpoint,
                        current_value=latency_ms,
                        expected_value=mean,
                        deviation=z_score,
                        context={"endpoint": endpoint},
                    )
                    anomaly = db_anomaly.to_dict()
                else:
                    anomaly = {
                        "type": AnomalyType.API_LATENCY.value,
                        "severity": severity.value,
                        "metric": endpoint,
                        "value": latency_ms,
                        "expected": mean,
                        "deviation": z_score,
                    }
        
        self._add_to_history(metric, latency_ms)
        return anomaly
    
    def check_error_rate(self, service: str, error_count: int, total: int, db: Session = None) -> Optional[dict]:
        """Check for error rate anomalies and persist if detected."""
        if total == 0:
            return None
        
        error_rate = error_count / total
        metric = f"error_rate:{service}"
        history = self._get_history(metric)
        
        anomaly = None
        if len(history) >= 5:
            z_score = self._calculate_z_score(error_rate, history)
            if z_score > self._z_threshold:
                mean = statistics.mean(history)
                severity = AnomalySeverity.CRITICAL if error_rate > 0.1 else AnomalySeverity.WARNING
                
                if db or self._db:
                    repo = AnomalyRepository(db or self._db)
                    db_anomaly = repo.save(
                        anomaly_type=AnomalyType.ERROR_RATE.value,
                        severity=severity.value,
                        metric_name=service,
                        current_value=error_rate,
                        expected_value=mean,
                        deviation=z_score,
                        context={"service": service, "error_count": error_count},
                    )
                    anomaly = db_anomaly.to_dict()
        
        self._add_to_history(metric, error_rate)
        return anomaly
