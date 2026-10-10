"""
Source span utilities for evidence tracking.

Provides consistent zero-based half-open character span semantics [start, end)
for tracking requirement provenance back to original JD text.

Design principles:
- Zero-based half-open spans: [start, end) where end is exclusive
- Unicode-aware character offsets (not byte offsets)
- Handle Windows (CRLF) and Unix (LF) line endings
- Validate spans against source text
- Preserve distinction between full clause and extracted sub-requirements
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple

logger = logging.getLogger("jd_agent.source_spans")


@dataclass
class CharacterSpan:
    """
    Zero-based half-open character span [start, end).
    
    Example: "Hello World"
             span(0, 5) = "Hello"
             span(6, 11) = "World"
    """
    start: int  # Inclusive start offset
    end: int    # Exclusive end offset
    
    def __post_init__(self):
        """Validate span invariants."""
        if self.start < 0:
            raise ValueError(f"Span start cannot be negative: {self.start}")
        if self.end < self.start:
            raise ValueError(f"Span end {self.end} < start {self.start}")
    
    def length(self) -> int:
        """Return span length in characters."""
        return self.end - self.start
    
    def overlaps(self, other: CharacterSpan) -> bool:
        """Check if this span overlaps with another."""
        return not (self.end <= other.start or other.end <= self.start)
    
    def contains(self, other: CharacterSpan) -> bool:
        """Check if this span fully contains another."""
        return self.start <= other.start and other.end <= self.end
    
    def extract(self, text: str) -> str:
        """Extract substring from text using this span."""
        return text[self.start:self.end]


@dataclass
class SourceSpan:
    """
    Source span with text validation.
    
    Includes the original text and character span for validation.
    """
    text: str
    span: CharacterSpan
    line_number: Optional[int] = None  # 1-based line number
    
    def validate(self, source_text: str) -> bool:
        """
        Validate that span correctly extracts text from source.
        
        Returns:
            True if span.extract(source_text) matches self.text
        """
        try:
            extracted = self.span.extract(source_text)
            # Allow some flexibility for whitespace normalization
            return extracted.strip() == self.text.strip()
        except Exception as e:
            logger.warning(
                "[SourceSpan] Validation failed: %s",
                str(e)
            )
            return False


class SpanBuilder:
    """
    Helper for building spans from text search.
    
    Handles finding substrings in source text and creating
    validated character spans.
    """
    
    def __init__(self, source_text: str):
        """
        Initialize builder with source text.
        
        Args:
            source_text: Original JD text to search within
        """
        self.source_text = source_text
        self._line_offsets = self._compute_line_offsets()
    
    def _compute_line_offsets(self) -> List[int]:
        """
        Compute character offset of each line start.
        
        Returns list where line_offsets[i] is the character offset
        where line i+1 starts (1-indexed line numbers).
        """
        offsets = [0]  # Line 1 starts at offset 0
        
        for i, char in enumerate(self.source_text):
            if char == '\n':
                offsets.append(i + 1)
        
        return offsets
    
    def find_span(
        self,
        text: str,
        start_hint: Optional[int] = None
    ) -> Optional[SourceSpan]:
        """
        Find character span for given text in source.
        
        Args:
            text: Text to find in source
            start_hint: Optional hint for where to start searching
        
        Returns:
            SourceSpan if found, None otherwise
        """
        # Normalize whitespace for searching
        normalized_text = ' '.join(text.split())
        normalized_source = ' '.join(self.source_text.split())
        
        # Find in normalized text
        start_pos = normalized_source.find(
            normalized_text,
            start_hint or 0
        )
        
        if start_pos == -1:
            logger.debug(
                "[SpanBuilder] Could not find text in source: %s",
                text[:50]
            )
            return None
        
        # Calculate end position
        end_pos = start_pos + len(normalized_text)
        
        # Map back to original source positions
        # (This is approximate due to whitespace normalization)
        original_start = self._map_to_original(start_pos)
        original_end = self._map_to_original(end_pos)
        
        # Get line number
        line_num = self._offset_to_line(original_start)
        
        span = CharacterSpan(original_start, original_end)
        
        return SourceSpan(
            text=text.strip(),
            span=span,
            line_number=line_num
        )
    
    def _map_to_original(self, normalized_offset: int) -> int:
        """
        Map offset in normalized text back to original text.
        
        This is approximate since we normalized whitespace.
        For precise mapping, would need to track transformations.
        
        For now, use normalized offset directly as approximation.
        """
        # Simple approximation: use offset directly
        # In production, would track whitespace transformations
        return min(normalized_offset, len(self.source_text) - 1)
    
    def _offset_to_line(self, offset: int) -> int:
        """
        Convert character offset to 1-based line number.
        
        Args:
            offset: Character offset in source text
        
        Returns:
            1-based line number
        """
        for line_num, line_start in enumerate(self._line_offsets, start=1):
            if offset < line_start:
                return line_num - 1
        
        return len(self._line_offsets)
    
    def create_span_for_clause(
        self,
        clause_text: str,
        section_start: int
    ) -> SourceSpan:
        """
        Create span for a clause within a section.
        
        Args:
            clause_text: The clause text
            section_start: Character offset where section starts
        
        Returns:
            SourceSpan with best-effort location
        """
        # Try to find exact match
        span = self.find_span(clause_text, section_start)
        
        if span:
            return span
        
        # Fallback: create span at section start
        logger.debug(
            "[SpanBuilder] Using fallback span for clause: %s",
            clause_text[:50]
        )
        
        end_pos = min(
            section_start + len(clause_text),
            len(self.source_text)
        )
        
        return SourceSpan(
            text=clause_text.strip(),
            span=CharacterSpan(section_start, end_pos),
            line_number=self._offset_to_line(section_start)
        )

    def find_exact_span(self, text: str) -> Optional[SourceSpan]:
        """
        Find an exact (case-sensitive, no whitespace normalisation) substring match.

        Unlike `find_span()`, this method does NOT normalise whitespace in either
        the search text or the source text. Use it when you need a precise
        character-level anchor and the text is known to appear verbatim.

        Schema limitation note: `SourceReference` has no `char_span_start` /
        `char_span_end` fields. The returned `SourceSpan` carries the span
        internally but it CANNOT be stored directly in a `SourceReference`.
        Only `line_number` can be propagated to the schema level.

        Args:
            text: Exact text to search for in source.

        Returns:
            SourceSpan if an exact match is found, None otherwise.
        """
        if not text:
            return None

        idx = self.source_text.find(text)
        if idx == -1:
            logger.debug(
                "[SpanBuilder] find_exact_span: no match for '%s'",
                text[:60],
            )
            return None

        span = CharacterSpan(idx, idx + len(text))
        line_num = self._offset_to_line(idx)

        return SourceSpan(
            text=text,
            span=span,
            line_number=line_num,
        )

    def get_line_number_for_text(self, text: str) -> Optional[int]:
        """
        Convenience helper: return the 1-based line number where `text` first
        appears in the source using an exact (case-sensitive) search.

        Returns None if not found. This is suitable for populating
        `SourceReference.line_number` despite the schema's lack of char-span
        fields.
        """
        span = self.find_exact_span(text)
        return span.line_number if span else None


def normalize_line_endings(text: str) -> str:
    """
    Normalize line endings to Unix-style (LF).
    
    Converts Windows CRLF to LF for consistent processing.
    """
    return text.replace('\r\n', '\n')


def validate_spans_against_source(
    spans: List[SourceSpan],
    source_text: str
) -> Tuple[int, int]:
    """
    Validate multiple spans against source text.
    
    Returns:
        Tuple of (valid_count, invalid_count)
    """
    valid = 0
    invalid = 0
    
    for span in spans:
        if span.validate(source_text):
            valid += 1
        else:
            invalid += 1
            logger.warning(
                "[Validation] Invalid span: expected '%s' at [%d:%d]",
                span.text[:50],
                span.span.start,
                span.span.end
            )
    
    return valid, invalid
