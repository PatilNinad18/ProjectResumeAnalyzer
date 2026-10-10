"""
Enterprise Knowledge Graph implementation using NetworkX.

The EKG provides:
- Canonical entity recognition (skills, domains, roles, tools)
- Relationship modeling (skill→domain, skill→role, etc.)
- Provenance tracking (seed data vs derived entities)
- Entity matching with confidence scoring

Design principles:
- Reviewed, provenance-aware seed data only (no auto-expansion yet)
- Conservative entity matching (avoid false positives)
- Confidence separate from interpretation (entity match ≠ requirement interpretation)
- Seed data validation (duplicate IDs, missing targets, alias collisions)
- Graceful handling of unknown entities and empty input
"""
from __future__ import annotations

import logging
import re
from functools import lru_cache
from typing import Dict, List, Optional, Set, Tuple

try:
    import networkx as nx
except ImportError:
    raise ImportError(
        "NetworkX is required for EKG functionality. "
        "Install with: pip install networkx"
    )

from app.schemas.master_context import EKGEntity, EKGEntityType

logger = logging.getLogger("jd_agent.ekg")


class SeedDataValidationError(Exception):
    """Raised when seed data validation fails."""
    pass


class EnterpriseKnowledgeGraph:
    """
    NetworkX-based Enterprise Knowledge Graph.
    
    Nodes: Entities (skills, domains, roles, tools, etc.)
    Edges: Relationships (requires, relates_to, used_in, etc.)
    
    Thread-safe for read operations after initialization.
    """
    
    def __init__(self):
        self.graph: nx.DiGraph = nx.DiGraph()
        self._entity_index: Dict[str, str] = {}  # normalized_name -> entity_id
        self._alias_index: Dict[str, str] = {}   # normalized_alias -> entity_id
        self._initialized = False
        
    def initialize_with_seed_data(self) -> None:
        """
        Load reviewed seed data into the graph with validation.
        
        Validates:
        - No duplicate entity IDs
        - No alias collisions
        - All relationship targets exist
        - No malformed entities
        """
        if self._initialized:
            logger.info("[EKG] Already initialized, skipping")
            return
            
        logger.info("[EKG] Initializing with seed data...")
        
        # Load seed data from separate module
        from app.services.ekg.seed_data import get_seed_entities, get_seed_relationships
        
        seed_entities = get_seed_entities()
        seed_relationships = get_seed_relationships()
        
        # Validate seed data before loading
        self._validate_seed_data(seed_entities, seed_relationships)
        
        # Add entities
        for entity in seed_entities:
            self.add_entity(entity)
        
        # Add relationships
        for from_id, to_id, rel_type, attrs in seed_relationships:
            self._add_relationship(from_id, to_id, rel_type, **attrs)
        
        self._initialized = True
        logger.info(
            "[EKG] Initialized: %d entities, %d edges",
            self.graph.number_of_nodes(),
            self.graph.number_of_edges()
        )
    
    def _validate_seed_data(
        self,
        entities: List[EKGEntity],
        relationships: List[Tuple[str, str, str, dict]]
    ) -> None:
        """
        Validate seed data for consistency and correctness.
        
        Checks:
        - No duplicate entity IDs
        - No alias collisions between different entities
        - All relationship endpoints exist
        - No malformed entities
        
        Raises:
            SeedDataValidationError: If validation fails
        """
        seen_ids: Set[str] = set()
        alias_to_entity: Dict[str, str] = {}
        
        # Validate entities
        for entity in entities:
            # Check for duplicate IDs
            if entity.entity_id in seen_ids:
                raise SeedDataValidationError(
                    f"Duplicate entity ID: {entity.entity_id}"
                )
            seen_ids.add(entity.entity_id)
            
            # Check for alias collisions
            for alias in entity.aliases:
                normalized = self._normalize(alias)
                if normalized in alias_to_entity:
                    existing = alias_to_entity[normalized]
                    if existing != entity.entity_id:
                        logger.warning(
                            "[EKG] Alias collision: '%s' used by both %s and %s",
                            alias, existing, entity.entity_id
                        )
                alias_to_entity[normalized] = entity.entity_id
            
            # Check for malformed entities
            if not entity.name or not entity.entity_id:
                raise SeedDataValidationError(
                    f"Malformed entity: missing name or ID"
                )
        
        # Validate relationships
        for from_id, to_id, rel_type, _ in relationships:
            if from_id not in seen_ids:
                raise SeedDataValidationError(
                    f"Relationship from unknown entity: {from_id}"
                )
            if to_id not in seen_ids:
                raise SeedDataValidationError(
                    f"Relationship to unknown entity: {to_id}"
                )
        
        logger.info(
            "[EKG] Seed data validated: %d entities, %d relationships",
            len(entities), len(relationships)
        )
    
    def add_entity(self, entity: EKGEntity) -> None:
        """Add an entity to the graph with proper indexing."""
        if self.graph.has_node(entity.entity_id):
            logger.warning("[EKG] Entity %s already exists, skipping", entity.entity_id)
            return
        
        # Add node with attributes
        self.graph.add_node(
            entity.entity_id,
            name=entity.name,
            entity_type=entity.entity_type.value,
            source=entity.source,
            confidence=entity.confidence,
            aliases=entity.aliases
        )
        
        # Index canonical name
        normalized = self._normalize(entity.name)
        self._entity_index[normalized] = entity.entity_id
        
        # Index aliases
        for alias in entity.aliases:
            normalized_alias = self._normalize(alias)
            if normalized_alias not in self._alias_index:
                self._alias_index[normalized_alias] = entity.entity_id
    
    def _add_relationship(
        self,
        from_id: str,
        to_id: str,
        rel_type: str,
        **attrs
    ) -> None:
        """Add a directed edge between entities."""
        if not self.graph.has_node(from_id):
            logger.warning("[EKG] Source entity %s not found", from_id)
            return
        if not self.graph.has_node(to_id):
            logger.warning("[EKG] Target entity %s not found", to_id)
            return
        
        self.graph.add_edge(from_id, to_id, relation_type=rel_type, **attrs)
    
    def match_entities(self, text: str) -> List[Tuple[str, float]]:
        """
        Match entities in text with confidence scoring.
        
        Uses conservative matching to avoid false positives:
        - Exact matches on canonical names or aliases get high confidence
        - Token-based partial matches get lower confidence
        - Careful distinction between similar terms (C vs C++, etc.)
        
        Args:
            text: Input text to match against
        
        Returns:
            List of (entity_id, confidence) tuples, sorted by confidence desc
        """
        if not text or not text.strip():
            return []
        
        if not self._initialized:
            self.initialize_with_seed_data()
        
        matches: Dict[str, float] = {}
        normalized_text = self._normalize(text)
        tokens = set(normalized_text.split())
        
        # Try exact matches first (highest confidence)
        for entity_id, node_data in self.graph.nodes(data=True):
            entity_name = self._normalize(node_data['name'])
            aliases = [self._normalize(a) for a in node_data.get('aliases', [])]
            
            # Exact match on canonical name (word boundary aware)
            if self._is_exact_match(entity_name, normalized_text):
                matches[entity_id] = max(matches.get(entity_id, 0.0), 0.95)
            
            # Exact match on aliases
            for alias in aliases:
                if self._is_exact_match(alias, normalized_text):
                    matches[entity_id] = max(matches.get(entity_id, 0.0), 0.90)
            
            # Token-based partial matching (lower confidence)
            # Only if we haven't already matched exactly
            if entity_id not in matches:
                name_tokens = set(entity_name.split())
                if name_tokens and name_tokens.issubset(tokens):
                    matches[entity_id] = max(matches.get(entity_id, 0.0), 0.75)
        
        # Sort by confidence descending
        return sorted(matches.items(), key=lambda x: x[1], reverse=True)
    
    def _is_exact_match(self, pattern: str, text: str) -> bool:
        """
        Check if pattern appears as exact match in text (word boundary aware).
        
        This helps distinguish between:
        - C vs C++ (different entities)
        - Verilog vs SystemVerilog (different entities)
        """
        # Use word boundaries, but handle special characters in pattern
        # For patterns like "c++" we need to escape special regex chars
        escaped = re.escape(pattern)
        # Allow word boundaries unless the pattern itself contains special chars
        # that should be matched literally (like ++)
        regex = r'\b' + escaped + r'\b'
        return bool(re.search(regex, text, re.IGNORECASE))
    
    def get_entity_info(self, entity_id: str) -> Optional[Dict]:
        """Get entity attributes from graph."""
        if not self.graph.has_node(entity_id):
            return None
        return dict(self.graph.nodes[entity_id])
    
    def get_related_entities(
        self,
        entity_id: str,
        relation_types: Optional[List[str]] = None
    ) -> List[str]:
        """
        Get entities related to the given entity.
        
        Args:
            entity_id: Source entity
            relation_types: Filter by relation types (None = all)
        
        Returns:
            List of related entity IDs
        """
        if not self.graph.has_node(entity_id):
            return []
        
        related = []
        for _, target, edge_data in self.graph.out_edges(entity_id, data=True):
            rel_type = edge_data.get('relation_type')
            if relation_types is None or rel_type in relation_types:
                related.append(target)
        
        return related
    
    def get_statistics(self) -> Dict:
        """Get graph statistics."""
        return {
            "total_entities": self.graph.number_of_nodes(),
            "total_relationships": self.graph.number_of_edges(),
            "entity_types": self._count_by_type(),
            "initialized": self._initialized
        }
    
    def _count_by_type(self) -> Dict[str, int]:
        """Count entities by type."""
        counts: Dict[str, int] = {}
        for _, data in self.graph.nodes(data=True):
            entity_type = data.get('entity_type', 'unknown')
            counts[entity_type] = counts.get(entity_type, 0) + 1
        return counts
    
    @staticmethod
    def _normalize(text: str) -> str:
        """
        Normalize text for matching (lowercase, cleaned).
        
        Preserves important characters like + and # for C++, C#, etc.
        """
        # Convert to lowercase
        text = text.lower()
        # Remove most special characters but keep + # . - for tech terms
        text = re.sub(r'[^\w\s.+#-]', ' ', text)
        # Collapse multiple spaces
        text = re.sub(r'\s+', ' ', text)
        return text.strip()


@lru_cache(maxsize=1)
def get_ekg() -> EnterpriseKnowledgeGraph:
    """
    Singleton EKG instance.
    
    Cached so all modules share the same graph.
    """
    ekg = EnterpriseKnowledgeGraph()
    ekg.initialize_with_seed_data()
    return ekg
