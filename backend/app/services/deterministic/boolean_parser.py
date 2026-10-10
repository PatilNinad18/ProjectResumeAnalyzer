"""
Boolean requirement parser for AND/OR/NOT logic.

Extracts and preserves Boolean relationships from requirement text:
- AND relationships: "Python and SQL are required"
- OR relationships: "Python or Java is required"
- Mixed structures: "Python and (PyTorch or TensorFlow)"
- Negation: handled by classifier, not as part of Boolean groups

Design principles:
- Extract individual atomic options from Boolean expressions
- Link options to corresponding requirements where schema supports
- Preserve original evidence and source spans
- Handle parentheses and explicit grouping
- Conservative parsing (avoid over-parsing natural language)
- Document schema limitations for nested structures
"""
from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from typing import List, Optional, Tuple

from app.schemas.master_context import (
    DisjunctionGroup,
    SourceReference,
    StructuredRequirement,
)

logger = logging.getLogger("jd_agent.boolean_parser")


@dataclass
class BooleanExpression:
    """Parsed Boolean expression."""
    operator: str  # "AND" or "OR"
    operands: List[str]  # Individual terms
    original_text: str
    has_parentheses: bool = False
    is_nested: bool = False


class BooleanParser:
    """
    Parser for Boolean requirement structures.
    
    Extracts individual options from OR/AND expressions while
    preserving source evidence.
    """
    
    def __init__(self):
        self._compile_patterns()
    
    def _compile_patterns(self):
        """Compile regex patterns for Boolean detection."""
        
        # OR patterns
        # Matches: "X or Y", "X, Y, or Z", "X/Y"
        self.or_simple = re.compile(
            r'\b(\w+(?:\s+\w+){0,2})\s+or\s+(\w+(?:\s+\w+){0,2})\b',
            re.IGNORECASE
        )
        
        self.or_list = re.compile(
            r'(?:\b\w+(?:\s+\w+){0,2}\s*,\s*)+(?:or\s+)?(\w+(?:\s+\w+){0,2})\b',
            re.IGNORECASE
        )
        
        self.or_slash = re.compile(
            r'\b(\w+(?:\s+\w+){0,2})/(\w+(?:\s+\w+){0,2})\b'
        )
        
        # AND patterns
        # Matches: "X and Y", "X, Y, and Z"
        self.and_simple = re.compile(
            r'\b(\w+(?:\s+\w+){0,2})\s+and\s+(\w+(?:\s+\w+){0,2})\b',
            re.IGNORECASE
        )
        
        # Parentheses pattern for nested expressions
        self.parentheses = re.compile(r'\(([^)]+)\)')
    
    def parse_disjunctions(
        self,
        requirements: List[StructuredRequirement]
    ) -> List[DisjunctionGroup]:
        """
        Parse OR groups from requirements.
        
        Creates DisjunctionGroup objects for requirements containing
        Boolean OR logic.
        
        Args:
            requirements: List of extracted requirements
        
        Returns:
            List of DisjunctionGroup objects
        """
        groups: List[DisjunctionGroup] = []
        
        for req in requirements:
            # Try to parse OR expressions
            or_expr = self._extract_or_expression(req.text)
            
            if or_expr and len(or_expr.operands) >= 2:
                # Create individual atomic requirements for each option
                option_reqs = self._create_option_requirements(
                    or_expr,
                    req
                )
                
                if len(option_reqs) >= 2:
                    # Create disjunction group
                    group = DisjunctionGroup(
                        group_id=f"disj_{uuid.uuid4().hex[:8]}",
                        operator="OR",
                        requirements=[opt.requirement_id for opt in option_reqs],
                        interpretation=self._generate_interpretation(or_expr, req)
                    )
                    groups.append(group)
                    
                    logger.debug(
                        "[BooleanParser] Created OR group: %s with %d options",
                        group.group_id, len(option_reqs)
                    )
        
        logger.info("[BooleanParser] Parsed %d disjunction groups", len(groups))
        return groups
    
    def _extract_or_expression(self, text: str) -> Optional[BooleanExpression]:
        """
        Extract OR expression from text.
        
        Handles:
        - "X or Y"
        - "X, Y, or Z"
        - "X/Y"
        
        Returns None if no clear OR pattern found.
        """
        # Try simple "X or Y" pattern first
        match = self.or_simple.search(text)
        if match:
            return BooleanExpression(
                operator="OR",
                operands=[match.group(1).strip(), match.group(2).strip()],
                original_text=match.group(0),
                has_parentheses=False
            )
        
        # Try slash pattern "X/Y"
        match = self.or_slash.search(text)
        if match:
            return BooleanExpression(
                operator="OR",
                operands=[match.group(1).strip(), match.group(2).strip()],
                original_text=match.group(0),
                has_parentheses=False
            )
        
        # Try list pattern "X, Y, or Z"
        operands = self._extract_or_list(text)
        if operands and len(operands) >= 2:
            return BooleanExpression(
                operator="OR",
                operands=operands,
                original_text=text,  # Use full text for list patterns
                has_parentheses=False
            )
        
        return None
    
    def _extract_or_list(self, text: str) -> List[str]:
        """
        Extract items from comma-separated OR list.
        
        Examples:
        - "Python, Java, or Go"
        - "React, Angular, or Vue"
        """
        # Look for pattern: item, item, ... or item
        # Split by comma, handle "or" before last item
        
        # First check if there's an "or" in the text
        if ' or ' not in text.lower():
            return []
        
        # Split by "or" and get the part before it
        parts = re.split(r'\s+or\s+', text, flags=re.IGNORECASE)
        if len(parts) < 2:
            return []
        
        # The last part after "or" is one operand
        last_item = parts[-1].strip()
        
        # The part before "or" might have comma-separated items
        before_or = parts[0]
        items = [item.strip() for item in before_or.split(',')]
        items = [item for item in items if item]  # Remove empty
        
        # Add the last item
        items.append(last_item)
        
        # Filter out very short items (likely articles/prepositions)
        items = [item for item in items if len(item) > 2]
        
        return items if len(items) >= 2 else []
    
    def _create_option_requirements(
        self,
        expr: BooleanExpression,
        parent_req: StructuredRequirement
    ) -> List[StructuredRequirement]:
        """
        Create individual StructuredRequirement objects for each option.
        
        Each option inherits priority and context from parent requirement
        but represents a distinct atomic alternative.
        """
        option_reqs: List[StructuredRequirement] = []
        
        for i, operand in enumerate(expr.operands):
            # Create a new requirement for this option
            option_req = StructuredRequirement(
                requirement_id=f"{parent_req.requirement_id}_opt_{i}",
                text=operand,
                clause_type=parent_req.clause_type,
                priority=parent_req.priority,
                matched_entities=[],  # Will be populated by EKG matching
                entity_confidence={},
                source=SourceReference(
                    text=operand,
                    section=parent_req.source.section,
                    line_number=parent_req.source.line_number
                ),
                is_explicit=parent_req.is_explicit,
                requires_clarification=False
            )
            option_reqs.append(option_req)
        
        return option_reqs
    
    def _generate_interpretation(
        self,
        expr: BooleanExpression,
        parent_req: StructuredRequirement
    ) -> str:
        """Generate human-readable interpretation of OR group."""
        items = expr.operands
        
        if len(items) == 2:
            return f"One of: {items[0]} OR {items[1]}"
        else:
            items_str = ", ".join(items[:-1])
            return f"One of: {items_str}, or {items[-1]}"
    
    def detect_and_relationships(
        self,
        requirements: List[StructuredRequirement]
    ) -> List[Tuple[str, ...]]:
        """
        Detect AND relationships between requirements.
        
        Note: Current schema (DisjunctionGroup) only supports OR.
        AND relationships are preserved in the requirement text but not
        as separate structured objects.
        
        This method documents detected AND patterns for future schema extension.
        
        Returns:
            List of tuples containing requirement IDs that have AND relationships
        """
        and_groups: List[Tuple[str, ...]] = []
        
        for req in requirements:
            # Look for "X and Y" pattern
            match = self.and_simple.search(req.text)
            if match:
                # Document the AND relationship
                and_groups.append((req.requirement_id,))
                logger.debug(
                    "[BooleanParser] Detected AND relationship in: %s",
                    req.text[:60]
                )
        
        if and_groups:
            logger.info(
                "[BooleanParser] Detected %d AND relationships (preserved in text, "
                "not structured - schema limitation)",
                len(and_groups)
            )
        
        return and_groups
    
    def detect_nested_structures(self, text: str) -> bool:
        """
        Detect nested Boolean structures like "X and (Y or Z)".
        
        Current schema limitation: DisjunctionGroup cannot represent
        nested Boolean logic.
        
        Returns:
            True if nested structure detected
        """
        # Check for parentheses
        if not self.parentheses.search(text):
            return False
        
        # Check for both AND and OR operators
        has_and = bool(self.and_simple.search(text))
        has_or = bool(self.or_simple.search(text))
        
        return has_and and has_or


def create_boolean_parser() -> BooleanParser:
    """Factory function to create parser instance."""
    return BooleanParser()
