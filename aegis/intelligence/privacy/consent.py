"""
Consent Management System
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session

from aegis.database import ConsentRepository


@dataclass
class ConsentRecord:
    """User consent record."""
    user_hash: str
    necessary: bool = True
    analytics: bool = False
    marketing: bool = False
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


class ConsentManager:
    """Manages user consent for GDPR/CCPA compliance."""
    
    CONSENT_TYPES = ["necessary", "analytics", "marketing"]
    
    def __init__(self, db: Session = None):
        self._db = db
        self._cache: dict[str, ConsentRecord] = {}
    
    def record_consent(
        self,
        user_hash: str,
        consent_type: str,
        granted: bool,
        ip_address: str = None,
        user_agent: str = None,
        db: Session = None
    ) -> bool:
        """Record user consent decision."""
        if consent_type not in self.CONSENT_TYPES:
            return False
        
        session = db or self._db
        if session:
            try:
                repo = ConsentRepository(session)
                repo.save(
                    user_hash=user_hash,
                    consent_type=consent_type,
                    granted=granted,
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
                return True
            except Exception:
                return False
        
        # Update cache
        if user_hash not in self._cache:
            self._cache[user_hash] = ConsentRecord(user_hash=user_hash)
        
        setattr(self._cache[user_hash], consent_type, granted)
        return True
    
    def get_consent(self, user_hash: str, db: Session = None) -> ConsentRecord:
        """Get current consent state for user."""
        # Check cache first
        if user_hash in self._cache:
            return self._cache[user_hash]
        
        # Check database
        session = db or self._db
        if session:
            try:
                repo = ConsentRepository(session)
                records = repo.get_latest(user_hash)
                
                consent = ConsentRecord(user_hash=user_hash)
                for record in records:
                    if hasattr(consent, record.consent_type):
                        setattr(consent, record.consent_type, record.granted)
                
                self._cache[user_hash] = consent
                return consent
            except Exception:
                pass
        
        # Return default consent (necessary only)
        return ConsentRecord(user_hash=user_hash)
    
    def can_track(self, user_hash: str, category: str, db: Session = None) -> bool:
        """Check if tracking is allowed for given category."""
        if category == "necessary":
            return True
        
        consent = self.get_consent(user_hash, db)
        return getattr(consent, category, False)
    
    def withdraw_all(self, user_hash: str, db: Session = None) -> bool:
        """Withdraw all non-necessary consent."""
        for consent_type in ["analytics", "marketing"]:
            self.record_consent(user_hash, consent_type, False, db=db)
        return True
