"""Frontmatter-driven scope building and source ranking.

This is the v0.2 addition that lets you tag Obsidian notes once and have
medstudy figure out scope automatically. Drop this in the frontmatter of
your notes:

    ---
    exam: prova1
    course: molecula_a_celula
    high_yield: true
    exam_weight: 0.9
    objectives: [glycolysis, krebs_cycle, etc]
    ---

Then run `medstudy scope --exam prova1 --from-frontmatter` and every note
matching `exam: prova1` is in scope, ranked by exam_weight × high_yield.
"""

from __future__ import annotations

from medstudy.models import Scope, Source


def scope_from_frontmatter(
    exam_name: str,
    sources: list[Source],
    *,
    require_exam_tag: bool = True,
) -> Scope:
    """Build a scope from notes whose YAML frontmatter contains `exam: <name>`.

    Args:
        exam_name: tag value to match (case-insensitive substring match).
        sources: ingested sources.
        require_exam_tag: if False, fall back to all sources when no
            frontmatter matches — useful for first runs before you've
            tagged anything.

    Returns:
        A Scope containing matching source_ids and any objectives found
        in matched frontmatters.
    """
    matched = [s for s in sources if s.matches_exam(exam_name)]
    if not matched and not require_exam_tag:
        matched = sources
    objectives: list[str] = []
    for s in matched:
        raw = s.frontmatter.get("objectives", [])
        if isinstance(raw, list):
            objectives.extend(str(x) for x in raw)
        elif isinstance(raw, str):
            objectives.append(raw)
    # dedupe while preserving order
    seen: set[str] = set()
    objectives = [o for o in objectives if not (o in seen or seen.add(o))]
    return Scope(
        exam_name=exam_name,
        source_ids=[s.source_id for s in matched],
        topics=objectives,
    )


def rank_sources(sources: list[Source]) -> list[Source]:
    """Order sources by likely exam value.

    Sort key (highest first):
        1. explicit exam_weight from frontmatter
        2. high_yield flag
        3. word count (longer notes tend to cover more ground)

    Use this when --max-cards is going to truncate output, so the cap
    falls on the lowest-priority sources rather than alphabetically.
    """
    return sorted(
        sources,
        key=lambda s: (-s.exam_weight, -int(s.is_high_yield), -s.word_count),
    )


def explain_ranking(sources: list[Source]) -> str:
    """Human-readable table of how sources are ranked. For CLI debugging."""
    ranked = rank_sources(sources)
    lines = ["rank  weight  hy  words  title"]
    for i, s in enumerate(ranked, start=1):
        lines.append(
            f"{i:>4}  {s.exam_weight:>6.2f}  {('Y' if s.is_high_yield else '-'):>2}  "
            f"{s.word_count:>5}  {s.title[:60]}"
        )
    return "\n".join(lines)
