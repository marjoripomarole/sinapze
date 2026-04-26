"""The two-pass extract-then-generate pipeline plus study guide generation.

This module orchestrates the LLM calls. The pipeline matches what the Brown
Alpert Med 2025 deployment found brought hallucination rates below the
acceptable threshold for medical content (~1 per 21 cards).
"""

from __future__ import annotations

import time
from collections.abc import Iterable
from typing import Any

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from medstudy.config import Settings, get_settings
from medstudy.llm import LLMClient
from medstudy.models import Card, Chunk, Fact, GuideSection, Source, StudyGuide
from medstudy.prompts import (
    CARDIFY_SYSTEM,
    CARDIFY_USER_TEMPLATE,
    EXTRACT_FACTS_SYSTEM,
    EXTRACT_FACTS_USER_TEMPLATE,
    GUIDE_BATCH_USER_TEMPLATE,
    GUIDE_SUMMARY_SYSTEM,
    GUIDE_SUMMARY_USER_TEMPLATE,
    GUIDE_SYSTEM,
    GUIDE_USER_TEMPLATE,
    VERIFY_SYSTEM,
    VERIFY_USER_TEMPLATE,
)

console = Console()


# ---------- helpers ---------------------------------------------------------


def _filter_chunks(
    chunks: list[Chunk],
    source_ids: list[str],
) -> list[Chunk]:
    sids = set(source_ids)
    return [c for c in chunks if c.source_id in sids]


def _detect_language(chunks: Iterable[Chunk]) -> str:
    sample = " ".join(c.text[:1500] for c in list(chunks)[:5]).lower()
    pt_markers = sum(sample.count(w) for w in (" é ", " são ", " ção", " não ", " que "))
    en_markers = sum(sample.count(w) for w in (" the ", " and ", " is ", " of "))
    return "pt-BR" if pt_markers > en_markers else "en"


# ---------- pass 1: extract atomic facts -----------------------------------


def extract_facts(
    chunks: list[Chunk],
    *,
    llm: LLMClient,
    max_facts_per_chunk: int = 15,
) -> list[Fact]:
    """Pass 1: extract atomic facts from each chunk.

    Each chunk is processed independently so a long source can't blow context.
    Cost: ~1 API call per chunk.
    """
    facts: list[Fact] = []
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task(
            f"Extracting facts from {len(chunks)} chunks…", total=len(chunks)
        )
        for chunk in chunks:
            user = EXTRACT_FACTS_USER_TEMPLATE.format(
                chunk_id=chunk.chunk_id,
                source_title=chunk.source_title,
                chunk_text=chunk.text,
                max_facts=max_facts_per_chunk,
            )
            try:
                raw = llm.complete_json(EXTRACT_FACTS_SYSTEM, user, max_tokens=4096)
            except Exception as e:  # noqa: BLE001
                console.print(f"[yellow]warn[/]: fact extraction failed for {chunk.chunk_id}: {e}")
                progress.advance(task)
                continue
            for item in raw or []:
                try:
                    facts.append(
                        Fact(
                            statement=item["statement"],
                            source_span=item["source_span"],
                            source_chunk_id=chunk.chunk_id,
                            topic=item.get("topic", "general"),
                            importance=item.get("importance", "medium"),
                        )
                    )
                except (KeyError, TypeError, ValueError):
                    continue
            progress.advance(task)
    console.print(f"[green]✓[/] extracted {len(facts)} atomic facts")
    return facts


# ---------- pass 2: cardify -------------------------------------------------


def _batched(seq: list[Any], n: int) -> Iterable[list[Any]]:
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


def cardify_facts(
    facts: list[Fact],
    *,
    exam_name: str,
    subject: str,
    llm: LLMClient,
    batch_size: int = 25,
) -> list[Card]:
    """Pass 2: convert facts into Anki cards.

    Batched so prompts fit in reasonable token windows and the model can
    spot intra-batch discrimination opportunities (drugs in same class etc.).
    """
    cards: list[Card] = []
    batches = list(_batched(facts, batch_size))
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task(f"Generating cards from {len(batches)} batches…", total=len(batches))
        for batch in batches:
            facts_payload = [
                {
                    "statement": f.statement,
                    "source_span": f.source_span,
                    "chunk_id": f.source_chunk_id,
                    "topic": f.topic,
                    "importance": f.importance,
                }
                for f in batch
            ]
            user = CARDIFY_USER_TEMPLATE.format(
                facts_json=_json_compact(facts_payload),
                exam_name=exam_name,
                subject=subject,
            )
            try:
                raw = llm.complete_json(CARDIFY_SYSTEM, user, max_tokens=8192)
            except Exception as e:  # noqa: BLE001
                console.print(f"[yellow]warn[/]: cardify failed: {e}")
                progress.advance(task)
                continue
            chunk_lookup = {f.source_span: f.source_chunk_id for f in batch}
            for item in raw or []:
                try:
                    span = item.get("source_span", "")
                    cards.append(
                        Card(
                            front=item["front"],
                            back=item.get("back", ""),
                            type=item.get("type", "cloze"),
                            tags=item.get("tags", []) + [f"exam::{_tag(exam_name)}"],
                            source_span=span,
                            source_chunk_id=chunk_lookup.get(span, batch[0].source_chunk_id),
                            explanation=item.get("explanation"),
                            mnemonic=item.get("mnemonic"),
                        )
                    )
                except (KeyError, TypeError, ValueError):
                    continue
            progress.advance(task)
    console.print(f"[green]✓[/] generated {len(cards)} cards (pre-verification)")
    return cards


# ---------- verifier pass --------------------------------------------------


def verify_cards(
    cards: list[Card],
    *,
    llm: LLMClient,
    batch_size: int = 20,
) -> list[Card]:
    """Pass 3: drop cards whose source_span doesn't entail their content.

    This is the single biggest hallucination reducer per the Nature 2025
    clinical-summarization work. ~30% extra token cost; worth it.
    """
    if not cards:
        return cards
    verified: list[Card] = []
    rejected = 0
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task(
            f"Verifying {len(cards)} cards against sources…",
            total=(len(cards) + batch_size - 1) // batch_size,
        )
        for batch in _batched(cards, batch_size):
            payload = [
                {
                    "card_index": i,
                    "front": c.front,
                    "back": c.back,
                    "source_span": c.source_span,
                }
                for i, c in enumerate(batch)
            ]
            try:
                raw = llm.complete_json(
                    VERIFY_SYSTEM,
                    VERIFY_USER_TEMPLATE.format(cards_json=_json_compact(payload)),
                    max_tokens=4096,
                )
            except Exception as e:  # noqa: BLE001
                console.print(f"[yellow]warn[/]: verifier failed for a batch: {e}; passing through")
                verified.extend(batch)
                progress.advance(task)
                continue
            verdicts = {item["card_index"]: item.get("entailed", False) for item in (raw or [])}
            for i, card in enumerate(batch):
                if verdicts.get(i, False):
                    card.verified = True
                    verified.append(card)
                else:
                    rejected += 1
            progress.advance(task)
    console.print(
        f"[green]✓[/] verified {len(verified)} / {len(cards)} cards "
        f"([red]{rejected} rejected[/] as not entailed by source)"
    )
    return verified


# ---------- public entry points --------------------------------------------


def generate_cards(
    chunks: list[Chunk],
    *,
    exam_name: str,
    subject: str,
    settings: Settings | None = None,
) -> list[Card]:
    """End-to-end card generation: extract → cardify → verify."""
    settings = settings or get_settings()
    llm = LLMClient(settings)
    facts = extract_facts(chunks, llm=llm)
    cards = cardify_facts(facts, exam_name=exam_name, subject=subject, llm=llm)
    if settings.verify_cards:
        cards = verify_cards(cards, llm=llm)
    return cards


def generate_study_guide(
    chunks: list[Chunk],
    *,
    exam_name: str,
    subject: str,
    course_description: str = "",
    settings: Settings | None = None,
) -> StudyGuide:
    """Generate a synthesis-focused study guide complementing the cards.

    Uses a single call when chunks fit within the model's context window.
    Falls back to map-reduce (sections per batch → final cheat-sheet synthesis)
    when the corpus is too large for one call.
    """
    settings = settings or get_settings()
    llm = LLMClient(settings)
    language = _detect_language(chunks)

    # Sort by title so related lecture content stays together in batches
    sorted_chunks = sorted(chunks, key=lambda c: c.source_title)

    # Tier-1 API limit: 30K input tokens/min. Keep each batch under ~20K tokens
    # of content (~80K chars) so total request stays under 30K with prompt overhead.
    MAX_CHARS = 80_000
    total_chars = sum(len(c.text) for c in sorted_chunks)

    console.print(f"[cyan]→[/] generating study guide ({len(chunks)} chunks, language={language})…")

    if total_chars <= MAX_CHARS:
        return _guide_single_call(
            sorted_chunks, exam_name, subject, course_description, language, llm, settings
        )
    return _guide_map_reduce(
        sorted_chunks, exam_name, subject, course_description, language, llm, settings
    )


def _make_chunks_block(chunks: list[Chunk]) -> str:
    return "\n\n".join(
        f"[chunk_id={c.chunk_id}] (from {c.source_title}"
        + (f", pp. {c.page_range[0]}-{c.page_range[1]}" if c.page_range else "")
        + f")\n{c.text}"
        for c in chunks
    )


def _parse_sections(raw_sections: list[Any]) -> list[GuideSection]:
    out = []
    for s in raw_sections:
        try:
            out.append(GuideSection(
                heading=s["heading"],
                summary=s["summary"],
                key_points=s.get("key_points", []),
                comparison_table_md=s.get("comparison_table_md"),
                flowchart_mermaid=s.get("flowchart_mermaid"),
                mnemonic=s.get("mnemonic"),
                source_chunks=s.get("source_chunks", []),
            ))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def _guide_single_call(
    chunks: list[Chunk],
    exam_name: str,
    subject: str,
    course_description: str,
    language: str,
    llm: LLMClient,
    settings: Settings,
) -> StudyGuide:
    user = GUIDE_USER_TEMPLATE.format(
        chunks_block=_make_chunks_block(chunks),
        exam_name=exam_name,
        subject=subject,
        course_description=course_description or "(none provided)",
    )
    raw = llm.complete_json(GUIDE_SYSTEM, user, max_tokens=settings.llm_max_tokens)
    sections = _parse_sections(raw.get("sections", []))
    guide = StudyGuide(
        exam_name=exam_name,
        subject=subject,
        language=raw.get("language", language),
        sections=sections,
        high_yield_summary=raw.get("high_yield_summary", ""),
    )
    console.print(f"[green]✓[/] study guide generated: {len(guide.sections)} sections")
    return guide


def _guide_map_reduce(
    chunks: list[Chunk],
    exam_name: str,
    subject: str,
    course_description: str,
    language: str,
    llm: LLMClient,
    settings: Settings,
) -> StudyGuide:
    """Map: generate sections per batch. Reduce: synthesise high-yield summary."""
    MAX_CHARS = 80_000
    batches: list[list[Chunk]] = []
    current: list[Chunk] = []
    current_size = 0
    for chunk in chunks:
        size = len(chunk.text)
        if current and current_size + size > MAX_CHARS:
            batches.append(current)
            current = [chunk]
            current_size = size
        else:
            current.append(chunk)
            current_size += size
    if current:
        batches.append(current)

    console.print(f"[cyan]→[/] map-reduce: {len(batches)} batches (30K token/min limit — ~65s between batches)…")
    all_sections: list[GuideSection] = []
    for i, batch in enumerate(batches, 1):
        if i > 1:
            console.print(f"[dim]  rate-limit pause 65s…[/]")
            time.sleep(65)
        console.print(f"[cyan]  batch {i}/{len(batches)} ({len(batch)} chunks)[/]")
        user = GUIDE_BATCH_USER_TEMPLATE.format(
            chunks_block=_make_chunks_block(batch),
            exam_name=exam_name,
            subject=subject,
            course_description=course_description or "(none provided)",
        )
        try:
            raw = llm.complete_json(GUIDE_SYSTEM, user, max_tokens=settings.llm_max_tokens)
            # Batch call returns a list (sections array), not the full guide object
            if isinstance(raw, list):
                all_sections.extend(_parse_sections(raw))
            elif isinstance(raw, dict):
                all_sections.extend(_parse_sections(raw.get("sections", [])))
        except Exception as e:  # noqa: BLE001
            console.print(f"[yellow]warn[/]: batch {i} failed: {e}")

    # Reduce: synthesise the high-yield cheat sheet from all section summaries
    sections_summary = "\n\n".join(
        f"## {s.heading}\n" + "\n".join(f"- {p}" for p in s.key_points)
        for s in all_sections
    )
    try:
        raw_summary = llm.complete_json(
            GUIDE_SUMMARY_SYSTEM,
            GUIDE_SUMMARY_USER_TEMPLATE.format(
                sections_summary=sections_summary,
                exam_name=exam_name,
                subject=subject,
            ),
            max_tokens=settings.llm_max_tokens,
        )
        high_yield = raw_summary.get("high_yield_summary", "")
    except Exception as e:  # noqa: BLE001
        console.print(f"[yellow]warn[/]: high-yield summary failed: {e}")
        high_yield = ""

    guide = StudyGuide(
        exam_name=exam_name,
        subject=subject,
        language=language,
        sections=all_sections,
        high_yield_summary=high_yield,
    )
    console.print(f"[green]✓[/] study guide generated: {len(guide.sections)} sections (map-reduce)")
    return guide


# ---------- internals -------------------------------------------------------


def _json_compact(obj: Any) -> str:
    import json as _json

    return _json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def _tag(name: str) -> str:
    return name.lower().replace(" ", "_").replace("-", "_")


def filter_chunks_for_scope(
    chunks: list[Chunk],
    sources: list[Source],
    source_ids: list[str],
) -> list[Chunk]:
    """Convenience wrapper for the CLI."""
    return _filter_chunks(chunks, source_ids)
