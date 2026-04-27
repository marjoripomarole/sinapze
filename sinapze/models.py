"""Data models. Pydantic so the LLM's structured output is validated."""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, computed_field


class Source(BaseModel):
    """A single ingested file (PDF or markdown note)."""

    path: Path
    kind: Literal["pdf", "markdown"]
    title: str
    text: str
    language: str = "auto"
    page_count: int | None = None
    word_count: int = 0
    ingested_at: datetime = Field(default_factory=datetime.utcnow)
    # YAML frontmatter from Obsidian markdown notes. Used for exam scoping
    # and ranking — keys we read: `exam`, `course`, `high_yield`, `exam_weight`,
    # `objectives`, `tags`. PDFs leave this empty.
    frontmatter: dict[str, Any] = Field(default_factory=dict)

    def matches_exam(self, exam_name: str) -> bool:
        """True if frontmatter tags this source for the given exam."""
        raw = self.frontmatter.get("exam")
        if raw is None:
            return False
        if isinstance(raw, str):
            return exam_name.lower() in raw.lower()
        if isinstance(raw, list):
            return any(exam_name.lower() in str(x).lower() for x in raw)
        return False

    @property
    def exam_weight(self) -> float:
        """Explicit exam_weight from frontmatter, default 0.5."""
        try:
            return float(self.frontmatter.get("exam_weight", 0.5))
        except (TypeError, ValueError):
            return 0.5

    @property
    def is_high_yield(self) -> bool:
        return bool(self.frontmatter.get("high_yield", False))

    @computed_field  # type: ignore[prop-decorator]
    @property
    def source_id(self) -> str:
        """Stable id from path; survives re-ingest."""
        return hashlib.sha256(str(self.path.resolve()).encode()).hexdigest()[:16]


class Chunk(BaseModel):
    """A semantic chunk of one source. Carries everything needed for citation."""

    source_id: str
    source_title: str
    source_path: Path
    chunk_index: int
    text: str
    page_range: tuple[int, int] | None = None  # for PDFs

    @computed_field  # type: ignore[prop-decorator]
    @property
    def chunk_id(self) -> str:
        return f"{self.source_id}:{self.chunk_index}"


class Fact(BaseModel):
    """An atomic fact extracted in pass 1, before being turned into a card."""

    statement: str
    source_span: str  # verbatim, ≤25 words
    source_chunk_id: str
    topic: str  # rough categorization, used for grouping
    importance: Literal["high", "medium", "low"] = "medium"


class Card(BaseModel):
    """An Anki flashcard, validated against research-backed constraints."""

    front: str
    back: str
    type: Literal["cloze", "basic", "image_occlusion"] = "cloze"
    tags: list[str] = Field(default_factory=list)
    source_span: str
    source_chunk_id: str
    explanation: str | None = None
    mnemonic: str | None = None
    verified: bool = False  # set true after verifier pass

    @computed_field  # type: ignore[prop-decorator]
    @property
    def card_id(self) -> str:
        """Deterministic id so re-runs don't duplicate cards in Anki."""
        h = hashlib.sha256(f"{self.front}|{self.back}".encode()).hexdigest()
        return h[:16]


class GuideSection(BaseModel):
    """One topical section of the study guide."""

    heading: str
    summary: str  # ≤3 paragraphs of synthesis
    key_points: list[str]
    comparison_table_md: str | None = None  # markdown table when applicable
    flowchart_mermaid: str | None = None  # mermaid for algorithms/pathways
    mnemonic: str | None = None
    source_chunks: list[str]  # chunk_ids cited


class StudyGuide(BaseModel):
    """Full study guide for one exam."""

    exam_name: str
    subject: str
    language: str
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    sections: list[GuideSection]
    high_yield_summary: str  # exam-day cheat sheet, 1 page max


class Scope(BaseModel):
    """Which sources cover which exam — your manual or LLM-assisted tagging."""

    exam_name: str
    source_ids: list[str]
    topics: list[str] = Field(default_factory=list)  # optional focus topics
    notes: str | None = None
