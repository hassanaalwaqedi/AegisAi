"""Database-backed official creator and project knowledge for Aegis."""

from .service import SystemKnowledgeService, get_system_knowledge_service

__all__ = ["SystemKnowledgeService", "get_system_knowledge_service"]
