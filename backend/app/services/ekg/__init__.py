"""
Enterprise Knowledge Graph (EKG) module.

Provides graph-based domain intelligence for JD extraction using NetworkX.
"""
from .knowledge_graph import EnterpriseKnowledgeGraph, get_ekg

__all__ = ["EnterpriseKnowledgeGraph", "get_ekg"]
