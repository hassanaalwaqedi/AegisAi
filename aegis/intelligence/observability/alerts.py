"""
Self-Healing Smart Alerts with Root Cause Explanation
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Callable


class AlertStatus(Enum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    AUTO_RESOLVED = "auto_resolved"


class AlertPriority(Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class RootCause:
    """Root cause analysis result"""
    description: str
    confidence: float
    evidence: list[str] = field(default_factory=list)
    suggested_actions: list[str] = field(default_factory=list)


@dataclass
class SmartAlert:
    """Alert with AI-generated context and root cause"""
    alert_id: str
    title: str
    description: str
    priority: AlertPriority
    status: AlertStatus
    created_at: datetime
    root_cause: Optional[RootCause] = None
    related_metrics: list[str] = field(default_factory=list)
    auto_heal_attempted: bool = False
    resolved_at: Optional[datetime] = None
    
    def to_dict(self) -> dict:
        return {
            "alert_id": self.alert_id,
            "title": self.title,
            "description": self.description,
            "priority": self.priority.name,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "root_cause": {
                "description": self.root_cause.description,
                "confidence": self.root_cause.confidence,
                "evidence": self.root_cause.evidence,
                "suggested_actions": self.root_cause.suggested_actions,
            } if self.root_cause else None,
            "related_metrics": self.related_metrics,
            "auto_heal_attempted": self.auto_heal_attempted,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
        }


class SmartAlertManager:
    """Manages alerts with AI-powered root cause analysis and self-healing"""
    
    def __init__(self):
        self._alerts: dict[str, SmartAlert] = {}
        self._alert_counter = 0
        self._heal_handlers: dict[str, Callable] = {}
    
    def _generate_id(self) -> str:
        self._alert_counter += 1
        return f"alert_{int(datetime.now().timestamp())}_{self._alert_counter}"
    
    def register_heal_handler(self, alert_type: str, handler: Callable):
        """Register a self-healing handler for alert type"""
        self._heal_handlers[alert_type] = handler
    
    def create_alert(
        self,
        title: str,
        description: str,
        priority: AlertPriority,
        alert_type: str = "general",
        context: dict = None
    ) -> SmartAlert:
        """Create an alert with automatic root cause analysis"""
        alert_id = self._generate_id()
        
        # Generate root cause analysis
        root_cause = self._analyze_root_cause(title, description, context or {})
        
        alert = SmartAlert(
            alert_id=alert_id,
            title=title,
            description=description,
            priority=priority,
            status=AlertStatus.OPEN,
            created_at=datetime.now(),
            root_cause=root_cause,
        )
        
        self._alerts[alert_id] = alert
        
        # Attempt self-healing for low/medium priority
        if priority in [AlertPriority.LOW, AlertPriority.MEDIUM]:
            self._attempt_self_heal(alert, alert_type, context or {})
        
        return alert
    
    def _analyze_root_cause(self, title: str, description: str, context: dict) -> RootCause:
        """AI-powered root cause analysis"""
        evidence = []
        suggested_actions = []
        cause_description = "Unknown root cause"
        confidence = 0.5
        
        # Pattern matching for common issues
        lower_desc = description.lower()
        
        if "latency" in lower_desc or "slow" in lower_desc:
            cause_description = "Elevated API response times detected"
            evidence.append("Response times exceeded baseline by significant margin")
            if "database" in lower_desc:
                evidence.append("Database queries may be causing bottleneck")
                suggested_actions.append("Check database connection pool utilization")
                suggested_actions.append("Review slow query logs")
            else:
                suggested_actions.append("Check upstream service health")
                suggested_actions.append("Review recent deployments")
            confidence = 0.75
        
        elif "error" in lower_desc or "exception" in lower_desc:
            cause_description = "Increased error rate in service"
            evidence.append("Error count exceeded normal threshold")
            suggested_actions.append("Check application logs for stack traces")
            suggested_actions.append("Verify external dependencies are healthy")
            confidence = 0.7
        
        elif "traffic" in lower_desc or "spike" in lower_desc:
            cause_description = "Unusual traffic pattern detected"
            evidence.append("Request volume deviated from historical baseline")
            suggested_actions.append("Verify if traffic is legitimate")
            suggested_actions.append("Check for potential DDoS or bot activity")
            confidence = 0.65
        
        return RootCause(
            description=cause_description,
            confidence=confidence,
            evidence=evidence,
            suggested_actions=suggested_actions,
        )
    
    def _attempt_self_heal(self, alert: SmartAlert, alert_type: str, context: dict) -> bool:
        """Attempt automatic remediation"""
        if alert_type not in self._heal_handlers:
            return False
        
        try:
            handler = self._heal_handlers[alert_type]
            success = handler(alert, context)
            alert.auto_heal_attempted = True
            
            if success:
                alert.status = AlertStatus.AUTO_RESOLVED
                alert.resolved_at = datetime.now()
            
            return success
        except Exception:
            return False
    
    def acknowledge(self, alert_id: str) -> bool:
        """Acknowledge an alert"""
        if alert_id in self._alerts:
            self._alerts[alert_id].status = AlertStatus.ACKNOWLEDGED
            return True
        return False
    
    def resolve(self, alert_id: str) -> bool:
        """Resolve an alert"""
        if alert_id in self._alerts:
            self._alerts[alert_id].status = AlertStatus.RESOLVED
            self._alerts[alert_id].resolved_at = datetime.now()
            return True
        return False
    
    def get_open_alerts(self) -> list[dict]:
        """Get all open alerts"""
        return [
            a.to_dict() for a in self._alerts.values()
            if a.status in [AlertStatus.OPEN, AlertStatus.ACKNOWLEDGED]
        ]
    
    def generate_incident_summary(self, alert_id: str) -> str:
        """Generate AI incident summary for an alert"""
        if alert_id not in self._alerts:
            return "Alert not found"
        
        alert = self._alerts[alert_id]
        summary = f"## Incident Summary: {alert.title}\n\n"
        summary += f"**Priority:** {alert.priority.name}\n"
        summary += f"**Status:** {alert.status.value}\n"
        summary += f"**Created:** {alert.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        summary += f"### Description\n{alert.description}\n\n"
        
        if alert.root_cause:
            summary += f"### Root Cause Analysis\n"
            summary += f"**Cause:** {alert.root_cause.description}\n"
            summary += f"**Confidence:** {alert.root_cause.confidence:.0%}\n\n"
            if alert.root_cause.evidence:
                summary += "**Evidence:**\n"
                for e in alert.root_cause.evidence:
                    summary += f"- {e}\n"
            if alert.root_cause.suggested_actions:
                summary += "\n**Suggested Actions:**\n"
                for a in alert.root_cause.suggested_actions:
                    summary += f"- {a}\n"
        
        return summary
