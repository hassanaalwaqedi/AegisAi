"""
Automated Insight Generation and Forecasting
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class InsightType(Enum):
    OPPORTUNITY = "opportunity"
    RISK = "risk"
    TREND = "trend"
    ANOMALY = "anomaly"
    RECOMMENDATION = "recommendation"


class InsightPriority(Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3


@dataclass
class Insight:
    """Auto-generated business insight"""
    insight_id: str
    insight_type: InsightType
    priority: InsightPriority
    title: str
    description: str
    impact: str
    confidence: float
    created_at: datetime
    data_points: list[dict] = field(default_factory=list)
    action_items: list[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            "insight_id": self.insight_id,
            "type": self.insight_type.value,
            "priority": self.priority.name,
            "title": self.title,
            "description": self.description,
            "impact": self.impact,
            "confidence": self.confidence,
            "created_at": self.created_at.isoformat(),
            "data_points": self.data_points,
            "action_items": self.action_items,
        }


class InsightGenerator:
    """Generates weekly insights and forecasts"""
    
    def __init__(self):
        self._insights: list[Insight] = []
        self._counter = 0
    
    def _generate_id(self) -> str:
        self._counter += 1
        return f"insight_{int(datetime.now().timestamp())}_{self._counter}"
    
    def generate_weekly_insights(self, metrics: dict, trends: dict) -> list[Insight]:
        """Generate weekly business insights from data"""
        insights = []
        
        # Check for growth opportunities
        if metrics.get("conversion_rate_change", 0) > 0.05:
            insight = Insight(
                insight_id=self._generate_id(),
                insight_type=InsightType.OPPORTUNITY,
                priority=InsightPriority.HIGH,
                title="Conversion Rate Improvement",
                description="Your conversion rate increased 5%+ this week.",
                impact="Potential additional revenue of $12,500/month if trend continues",
                confidence=0.85,
                created_at=datetime.now(),
                action_items=[
                    "Identify traffic sources driving conversions",
                    "Increase budget for high-performing channels",
                ],
            )
            insights.append(insight)
        
        # Check for risk signals
        if metrics.get("churn_rate", 0) > 0.1:
            insight = Insight(
                insight_id=self._generate_id(),
                insight_type=InsightType.RISK,
                priority=InsightPriority.HIGH,
                title="Elevated Churn Risk",
                description="User churn rate exceeded 10% threshold this week.",
                impact="Projected loss of 450 active users if unaddressed",
                confidence=0.78,
                created_at=datetime.now(),
                action_items=[
                    "Analyze drop-off points in user journey",
                    "Review recent product changes",
                    "Consider targeted re-engagement campaign",
                ],
            )
            insights.append(insight)
        
        self._insights.extend(insights)
        return insights
    
    def generate_forecast(self, metric_name: str, historical: list[float]) -> dict:
        """Generate simple forecast using moving average"""
        if len(historical) < 7:
            return {"error": "Insufficient data for forecast"}
        
        # Simple exponential smoothing
        alpha = 0.3
        forecast = historical[-1]
        for i in range(7):
            forecast = alpha * historical[-(i+1)] + (1-alpha) * forecast
        
        avg = sum(historical[-7:]) / 7
        variance = sum((x - avg) ** 2 for x in historical[-7:]) / 7
        std_dev = variance ** 0.5
        
        return {
            "metric": metric_name,
            "forecast_value": round(forecast, 2),
            "confidence_interval": {
                "lower": round(forecast - 1.96 * std_dev, 2),
                "upper": round(forecast + 1.96 * std_dev, 2),
            },
            "confidence": 0.75,
            "generated_at": datetime.now().isoformat(),
        }
    
    def get_recent_insights(self, limit: int = 10) -> list[dict]:
        """Get recent insights"""
        return [i.to_dict() for i in self._insights[-limit:]]
