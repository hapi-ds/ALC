"""Pydantic v2 schemas for sanitized structured content.

Defines the unified StructuredContent model produced by the Sanitization_Pipeline
regardless of input format (PDF, HTML, XML/JATS). Downstream consumers (embedding
generation, literature review agents) depend on this schema contract.

References:
    - Requirements 16.1, 16.3, 16.4, 16.5
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ─── Enums ────────────────────────────────────────────────────────────────────


class SourceFormat(StrEnum):
    """Original file format of the ingested content.

    Used to record which sanitizer processed the file.
    """

    PDF = "pdf"
    HTML = "html"
    XML = "xml"


# ─── Supporting Models ────────────────────────────────────────────────────────


class BodySection(BaseModel):
    """A single section extracted from the document body.

    Attributes:
        heading: Section heading text (may be empty for untitled sections).
        text: Section body text content.
    """

    heading: str
    text: str


# ─── StructuredContent ────────────────────────────────────────────────────────


class StructuredContent(BaseModel):
    """Unified structured content produced by the Sanitization_Pipeline.

    This frozen model guarantees internal consistency between raw_plaintext,
    word_count, and the component fields (title, abstract, body sections).
    Downstream consumers can rely on these invariants without re-validation.

    Attributes:
        source_format: Original file format that was sanitized.
        extracted_title: Title extracted from the document.
        extracted_abstract: Abstract extracted from the document.
        body_sections: Ordered list of heading + text section pairs.
        references: List of citation strings extracted from the document.
        figure_count: Number of figures detected in the document.
        table_count: Number of tables detected in the document.
        word_count: Whitespace-delimited token count of raw_plaintext.
        raw_plaintext: Concatenation of title, abstract, and body section
            texts separated by newline characters.
    """

    model_config = ConfigDict(frozen=True)

    source_format: SourceFormat
    extracted_title: str
    extracted_abstract: str
    body_sections: list[BodySection]
    references: list[str] = Field(default_factory=list)
    figure_count: int = Field(ge=0)
    table_count: int = Field(ge=0)
    word_count: int = Field(ge=0)
    raw_plaintext: str

    @model_validator(mode="after")
    def _validate_consistency(self) -> StructuredContent:
        """Validate internal consistency constraints.

        Ensures that:
            1. word_count equals the number of whitespace-delimited tokens
               in raw_plaintext.
            2. raw_plaintext equals the newline-joined concatenation of
               extracted_title, extracted_abstract, and all body section texts.

        Raises:
            ValueError: If either consistency constraint is violated.
        """
        expected_plaintext = "\n".join(
            [
                self.extracted_title,
                self.extracted_abstract,
                *[s.text for s in self.body_sections],
            ]
        )
        if self.raw_plaintext != expected_plaintext:
            msg = (
                "raw_plaintext must equal the newline-joined concatenation of "
                "extracted_title, extracted_abstract, and body_sections texts"
            )
            raise ValueError(msg)

        expected_word_count = len(self.raw_plaintext.split())
        if self.word_count != expected_word_count:
            msg = (
                f"word_count ({self.word_count}) must equal "
                f"len(raw_plaintext.split()) ({expected_word_count})"
            )
            raise ValueError(msg)

        return self
