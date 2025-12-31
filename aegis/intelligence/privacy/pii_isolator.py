"""
Privacy & PII Isolation - Zero-Trust Data Access
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Callable
import hashlib
import re


class DataClassification(Enum):
    """Data sensitivity levels."""
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    PII = "pii"
    SENSITIVE_PII = "sensitive_pii"


class AccessLevel(Enum):
    """User access levels."""
    ANONYMOUS = 0
    AUTHENTICATED = 1
    ANALYST = 2
    ADMIN = 3
    SUPERADMIN = 4


@dataclass
class PIIField:
    """Definition of a PII field."""
    name: str
    classification: DataClassification
    mask_pattern: str = "***"
    hash_salt: str = ""


@dataclass
class AccessContext:
    """Context for access control decisions."""
    user_id: str
    access_level: AccessLevel
    purpose: str
    ip_address: Optional[str] = None
    consent_granted: bool = False
    audit_log: bool = True


class PIIIsolator:
    """Zero-trust PII isolation and masking."""
    
    # Common PII patterns
    PII_PATTERNS = {
        "email": re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),
        "phone": re.compile(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b'),
        "ssn": re.compile(r'\b\d{3}-\d{2}-\d{4}\b'),
        "credit_card": re.compile(r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b'),
        "ip_address": re.compile(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b'),
    }
    
    # Field classifications
    FIELD_CLASSIFICATIONS = {
        "email": DataClassification.PII,
        "phone": DataClassification.PII,
        "name": DataClassification.PII,
        "address": DataClassification.PII,
        "ssn": DataClassification.SENSITIVE_PII,
        "credit_card": DataClassification.SENSITIVE_PII,
        "ip_address": DataClassification.CONFIDENTIAL,
        "user_agent": DataClassification.INTERNAL,
        "session_id": DataClassification.INTERNAL,
    }
    
    def __init__(self, salt: str = "aegis_pii_salt"):
        self._salt = salt
        self._audit_log: list[dict] = []
    
    def hash_pii(self, value: str, field_type: str = "") -> str:
        """One-way hash PII for analytics while preserving privacy."""
        salted = f"{self._salt}:{field_type}:{value}"
        return hashlib.sha256(salted.encode()).hexdigest()[:16]
    
    def mask_value(self, value: str, field_type: str) -> str:
        """Mask sensitive value based on field type."""
        if not value:
            return ""
        
        if field_type == "email":
            parts = value.split("@")
            if len(parts) == 2:
                return f"{parts[0][0]}***@{parts[1]}"
        elif field_type == "phone":
            return f"***-***-{value[-4:]}" if len(value) >= 4 else "***"
        elif field_type == "credit_card":
            return f"****-****-****-{value[-4:]}" if len(value) >= 4 else "****"
        elif field_type == "name":
            return f"{value[0]}***" if value else "***"
        elif field_type == "ip_address":
            parts = value.split(".")
            if len(parts) == 4:
                return f"{parts[0]}.{parts[1]}.*.*"
        
        return "***"
    
    def detect_pii(self, text: str) -> list[tuple[str, str]]:
        """Detect PII patterns in text."""
        detected = []
        for pii_type, pattern in self.PII_PATTERNS.items():
            matches = pattern.findall(text)
            for match in matches:
                detected.append((pii_type, match))
        return detected
    
    def sanitize_text(self, text: str) -> str:
        """Remove all detected PII from text."""
        sanitized = text
        for pii_type, pattern in self.PII_PATTERNS.items():
            sanitized = pattern.sub(f"[{pii_type.upper()}_REDACTED]", sanitized)
        return sanitized
    
    def sanitize_dict(self, data: dict, context: AccessContext) -> dict:
        """Sanitize dictionary based on access level."""
        sanitized = {}
        
        for key, value in data.items():
            classification = self.FIELD_CLASSIFICATIONS.get(
                key, DataClassification.PUBLIC
            )
            
            # Check if user can access this field
            if self._can_access(classification, context):
                sanitized[key] = value
            else:
                # Mask or hash based on classification
                if classification in [DataClassification.PII, DataClassification.SENSITIVE_PII]:
                    sanitized[key] = self.mask_value(str(value), key)
                else:
                    sanitized[key] = "[REDACTED]"
        
        # Log access
        if context.audit_log:
            self._log_access(context, data.keys())
        
        return sanitized
    
    def _can_access(self, classification: DataClassification, context: AccessContext) -> bool:
        """Check if user can access data of given classification."""
        access_requirements = {
            DataClassification.PUBLIC: AccessLevel.ANONYMOUS,
            DataClassification.INTERNAL: AccessLevel.AUTHENTICATED,
            DataClassification.CONFIDENTIAL: AccessLevel.ANALYST,
            DataClassification.PII: AccessLevel.ADMIN,
            DataClassification.SENSITIVE_PII: AccessLevel.SUPERADMIN,
        }
        
        required_level = access_requirements.get(classification, AccessLevel.SUPERADMIN)
        
        # Consent required for PII
        if classification in [DataClassification.PII, DataClassification.SENSITIVE_PII]:
            if not context.consent_granted:
                return False
        
        return context.access_level.value >= required_level.value
    
    def _log_access(self, context: AccessContext, fields: list):
        """Log data access for audit."""
        self._audit_log.append({
            "timestamp": datetime.now().isoformat(),
            "user_id": self.hash_pii(context.user_id, "user_id"),
            "access_level": context.access_level.name,
            "purpose": context.purpose,
            "fields_accessed": list(fields),
            "ip_hash": self.hash_pii(context.ip_address or "", "ip") if context.ip_address else None,
        })
    
    def get_audit_log(self, limit: int = 100) -> list[dict]:
        """Get recent audit log entries."""
        return self._audit_log[-limit:]
