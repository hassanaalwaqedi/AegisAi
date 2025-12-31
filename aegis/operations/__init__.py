"""
AegisAI - Operations Module

Restaurant and retail operational intelligence.

Modules:
- employee_monitor: Staff tracking and coverage analysis
- queue_analyzer: Customer queue detection and wait times
- service_kpi: Service speed and efficiency metrics
- safety_rules: Uniform and hygiene compliance

Copyright 2024 AegisAI Project
"""

from aegis.operations.employee_monitor import EmployeeMonitor
from aegis.operations.queue_analyzer import QueueAnalyzer
from aegis.operations.service_kpi import ServiceKPITracker
from aegis.operations.safety_rules import SafetyRulesChecker

__all__ = [
    "EmployeeMonitor",
    "QueueAnalyzer", 
    "ServiceKPITracker",
    "SafetyRulesChecker"
]
