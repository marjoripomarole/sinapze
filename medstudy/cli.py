"""CLI entry points: ingest, scope, scope-from-tags, rank, guide, cards, plan."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from medstudy.config import get_settings
from medstudy.export import export_anki_deck, export_markdown_guide
from medstudy.generate import (
    filter_chunks_for_scope,
    generate_cards,
    generate_study_guide,
)
from medstudy.ingest import (
    _persist,
    auto_scope_from_sources,
    ingest_directory,
    load_persisted,
    load_scope,
    save_scope,
)
from medstudy.plan import generate_cram_plan
from medstudy.scope import explain_ranking, rank_sources, scope_from_frontmatter

console = Console()


@click.group()
def cli() -> None:
    """medstudy — source-grounded study material generator."""


@cli.command()
@click.option("--source", "source_dirs", required=True, multiple=True, type=click.Path(exists=True, path_type=Path))
@click.option("--exam", "exam_name", default=None, help="Auto-create a scope for this exam from all ingested files.")
@click.option("--keyword", default=None, help="Filter sources by keyword in title/content (only with --exam).")
def ingest(source_dirs: tuple[Path, ...], exam_name: str | None, keyword: str | None) -> None:
    """Walk one or more directories of PDFs and Obsidian notes, parse and chunk them."""
    settings = get_settings()
    all_sources: list = []
    all_chunks: list = []
    for source_dir in source_dirs:
        s, c = ingest_directory(source_dir, persist=False)
        all_sources.extend(s)
        all_chunks.extend(c)
    _persist(settings.data_dir, all_sources, all_chunks)
    sources, chunks = all_sources, all_chunks

    table = Table(title="Ingested sources")
    table.add_column("Title", style="cyan")
    table.add_column("Kind")
    table.add_column("Lang")
    table.add_column("Words", justify="right")
    table.add_column("Chunks", justify="right")
    chunks_per_source: dict[str, int] = {}
    for c in chunks:
        chunks_per_source[c.source_id] = chunks_per_source.get(c.source_id, 0) + 1
    for s in sources:
        table.add_row(
            s.title[:50],
            s.kind,
            s.language,
            str(s.word_count),
            str(chunks_per_source.get(s.source_id, 0)),
        )
    console.print(table)
    console.print(f"[green]✓[/] {len(sources)} sources, {len(chunks)} chunks")

    if exam_name:
        scope = auto_scope_from_sources(exam_name, sources, keyword)
        save_scope(scope)
        console.print(
            f"[green]✓[/] auto-scope for [bold]{exam_name}[/] "
            f"({len(scope.source_ids)} sources)"
        )


@cli.command()
@click.option("--exam", "exam_name", required=True)
@click.option("--include", multiple=True, help="Substring(s) to match in source title.")
@click.option("--exclude", multiple=True, help="Substring(s) to exclude.")
def scope(exam_name: str, include: tuple[str, ...], exclude: tuple[str, ...]) -> None:
    """Define which ingested sources cover a given exam."""
    sources, _ = load_persisted()
    matched = sources
    if include:
        matched = [s for s in matched if any(i.lower() in s.title.lower() for i in include)]
    if exclude:
        matched = [s for s in matched if not any(e.lower() in s.title.lower() for e in exclude)]

    table = Table(title=f"Scope for {exam_name}")
    table.add_column("Title", style="cyan")
    table.add_column("Kind")
    for s in matched:
        table.add_row(s.title[:60], s.kind)
    console.print(table)

    s_obj = auto_scope_from_sources(exam_name, matched, None)
    save_scope(s_obj)
    console.print(f"[green]✓[/] saved scope ({len(matched)} sources)")


@cli.command()
@click.option("--exam", "exam_name", required=True)
@click.option("--output", "output_path", required=True, type=click.Path(path_type=Path))
@click.option("--subject", default="biochemistry")
@click.option("--course-description", default="")
def guide(exam_name: str, output_path: Path, subject: str, course_description: str) -> None:
    """Generate a synthesis-focused study guide for an exam."""
    sources, all_chunks = load_persisted()
    scope_obj = load_scope(exam_name)
    chunks = filter_chunks_for_scope(all_chunks, sources, scope_obj.source_ids)
    if not chunks:
        console.print("[red]No chunks for that scope. Run `medstudy scope` first.[/]")
        raise click.Abort()
    guide_obj = generate_study_guide(
        chunks,
        exam_name=exam_name,
        subject=subject,
        course_description=course_description,
    )
    out = export_markdown_guide(guide_obj, output_path)
    console.print(f"[green]✓[/] study guide → [bold]{out}[/]")


@cli.command()
@click.option("--exam", "exam_name", required=True)
@click.option("--output", "output_path", required=True, type=click.Path(path_type=Path))
@click.option("--subject", default="biochemistry")
@click.option("--max-cards", default=400, type=int)
def cards(exam_name: str, output_path: Path, subject: str, max_cards: int) -> None:
    """Generate Anki cards (.apkg) for an exam."""
    sources, all_chunks = load_persisted()
    scope_obj = load_scope(exam_name)
    chunks = filter_chunks_for_scope(all_chunks, sources, scope_obj.source_ids)
    if not chunks:
        console.print("[red]No chunks for that scope.[/]")
        raise click.Abort()

    cards_list = generate_cards(chunks, exam_name=exam_name, subject=subject)
    if len(cards_list) > max_cards:
        # Prefer high-yield tagged cards if we need to trim
        cards_list.sort(key=lambda c: (-int("high_yield" in c.tags), c.front))
        cards_list = cards_list[:max_cards]

    out = export_anki_deck(cards_list, output_path, deck_name=exam_name)
    console.print(f"[green]✓[/] {len(cards_list)} cards → [bold]{out}[/]")
    console.print("[dim]Import with: File → Import in the Anki desktop app[/]")

    # Also save JSON for the web UI
    import json as _json
    json_out = get_settings().data_dir / f"cards__{exam_name}.json"
    json_out.write_text(
        _json.dumps({"exam": exam_name, "cards": [c.model_dump() for c in cards_list]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    console.print(f"[dim]Web UI card data → {json_out}[/]")


@cli.command(name="scope-from-tags")
@click.option("--exam", "exam_name", required=True)
@click.option(
    "--fallback-all/--no-fallback-all",
    default=False,
    help="If no notes match in frontmatter, include everything (useful before tagging).",
)
def scope_from_tags(exam_name: str, fallback_all: bool) -> None:
    """Build scope from YAML frontmatter `exam:` tags in your Obsidian notes.

    Add to your note frontmatter:
      ---
      exam: prova1
      high_yield: true
      exam_weight: 0.9
      objectives: [glycolysis, krebs]
      ---
    """
    sources, _ = load_persisted()
    s_obj = scope_from_frontmatter(exam_name, sources, require_exam_tag=not fallback_all)
    matched = [s for s in sources if s.source_id in set(s_obj.source_ids)]

    table = Table(title=f"Frontmatter scope for {exam_name}")
    table.add_column("Title", style="cyan")
    table.add_column("Weight", justify="right")
    table.add_column("HY")
    table.add_column("Words", justify="right")
    for s in rank_sources(matched):
        table.add_row(
            s.title[:50],
            f"{s.exam_weight:.2f}",
            "✓" if s.is_high_yield else "",
            str(s.word_count),
        )
    console.print(table)
    if s_obj.topics:
        console.print(f"[dim]Objectives ({len(s_obj.topics)}):[/] {', '.join(s_obj.topics[:10])}")
    save_scope(s_obj)
    console.print(f"[green]✓[/] saved scope ({len(matched)} sources)")


@cli.command()
def rank() -> None:
    """Show source ranking by exam_weight × high_yield × length."""
    sources, _ = load_persisted()
    console.print(explain_ranking(sources))


@cli.command()
@click.option("--exam", "exam_name", required=True)
@click.option(
    "--exam-datetime",
    "exam_dt",
    required=True,
    help="ISO format, e.g. 2026-04-28T09:00",
)
@click.option("--guide", "guide_path", default="./out/guide.md")
@click.option("--deck", "deck_path", default="./out/deck.apkg")
@click.option("--lang", default="en", type=click.Choice(["en", "pt-BR"]))
@click.option("--output", "output_path", default="./out/cram_plan.md", type=click.Path(path_type=Path))
def plan(
    exam_name: str,
    exam_dt: str,
    guide_path: str,
    deck_path: str,
    lang: str,
    output_path: Path,
) -> None:
    """Generate a 24-hour, 6-pass cram schedule anchored to your exam time."""
    try:
        dt = datetime.fromisoformat(exam_dt)
    except ValueError as e:
        console.print(f"[red]Bad datetime:[/] {e}. Use ISO like 2026-04-28T09:00.")
        raise click.Abort()
    md = generate_cram_plan(
        exam_name=exam_name,
        exam_datetime=dt,
        guide_path=guide_path,
        deck_path=deck_path,
        language=lang,
    )
    output_path = output_path.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(md, encoding="utf-8")
    console.print(f"[green]✓[/] cram plan → [bold]{output_path}[/]")


@cli.command()
def doctor() -> None:
    """Verify environment and show current settings."""
    try:
        s = get_settings()
    except Exception as e:  # noqa: BLE001
        console.print(f"[red]Settings error:[/] {e}")
        raise click.Abort()
    console.print("[green]✓[/] settings loaded")
    console.print(f"  model            = {s.llm_model}")
    console.print(f"  temperature      = {s.llm_temperature}")
    console.print(f"  data_dir         = {s.data_dir.resolve()}")
    console.print(f"  verify_cards     = {s.verify_cards}")
    console.print(f"  default_language = {s.default_language}")


if __name__ == "__main__":
    cli()
