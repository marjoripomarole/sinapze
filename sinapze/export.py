"""Exporters for Anki .apkg and Markdown study guides."""

from __future__ import annotations

import random
from pathlib import Path

import genanki

from sinapze.models import Card, StudyGuide

# Stable model IDs so re-imports update existing cards rather than duplicating.
# Generated once with random.randrange(1 << 30, 1 << 31).
_BASIC_MODEL_ID = 1607392319
_CLOZE_MODEL_ID = 1607392320

_CARD_CSS = """
.card {
  font-family: -apple-system, BlinkMacSystemFont, sans-serif;
  font-size: 18px;
  text-align: left;
  color: #222;
  background: #fafafa;
  padding: 16px;
  line-height: 1.5;
}
.cloze { font-weight: bold; color: #1a73e8; }
.source { font-size: 12px; color: #888; margin-top: 16px; border-top: 1px solid #ddd; padding-top: 8px; }
.explanation { font-size: 14px; color: #555; margin-top: 12px; font-style: italic; }
.mnemonic { font-size: 14px; color: #6a1b9a; margin-top: 8px; }
.tags { font-size: 11px; color: #aaa; margin-top: 8px; }
"""

_BASIC_MODEL = genanki.Model(
    _BASIC_MODEL_ID,
    "sinapze Basic",
    fields=[
        {"name": "Front"},
        {"name": "Back"},
        {"name": "Explanation"},
        {"name": "Mnemonic"},
        {"name": "Source"},
        {"name": "Tags"},
    ],
    templates=[
        {
            "name": "Card 1",
            "qfmt": "{{Front}}",
            "afmt": (
                "{{FrontSide}}<hr id='answer'>{{Back}}"
                "{{#Explanation}}<div class='explanation'>{{Explanation}}</div>{{/Explanation}}"
                "{{#Mnemonic}}<div class='mnemonic'>Mnemônico: {{Mnemonic}}</div>{{/Mnemonic}}"
                "{{#Source}}<div class='source'>Fonte: {{Source}}</div>{{/Source}}"
            ),
        }
    ],
    css=_CARD_CSS,
)

_CLOZE_MODEL = genanki.Model(
    _CLOZE_MODEL_ID,
    "sinapze Cloze",
    model_type=genanki.Model.CLOZE,
    fields=[
        {"name": "Text"},
        {"name": "Explanation"},
        {"name": "Mnemonic"},
        {"name": "Source"},
        {"name": "Tags"},
    ],
    templates=[
        {
            "name": "Cloze",
            "qfmt": "{{cloze:Text}}",
            "afmt": (
                "{{cloze:Text}}"
                "{{#Explanation}}<div class='explanation'>{{Explanation}}</div>{{/Explanation}}"
                "{{#Mnemonic}}<div class='mnemonic'>Mnemônico: {{Mnemonic}}</div>{{/Mnemonic}}"
                "{{#Source}}<div class='source'>Fonte: {{Source}}</div>{{/Source}}"
            ),
        }
    ],
    css=_CARD_CSS,
)


def _deck_id(exam_name: str) -> int:
    """Stable deck id derived from exam name so re-import merges, not duplicates."""
    h = abs(hash(exam_name)) % (1 << 30)
    return (1 << 30) + h


def export_anki_deck(
    cards: list[Card],
    output_path: Path,
    *,
    deck_name: str,
) -> Path:
    """Write a .apkg file ready to import into Anki/AnkiMobile.

    Cards keep stable ids (hash of front+back) so re-imports update existing
    cards without losing your review history.
    """
    output_path = output_path.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    deck = genanki.Deck(_deck_id(deck_name), deck_name)

    for card in cards:
        source_str = f"{card.source_chunk_id} — “{card.source_span}”"
        if card.type == "cloze":
            note = genanki.Note(
                model=_CLOZE_MODEL,
                fields=[
                    card.front,
                    card.explanation or "",
                    card.mnemonic or "",
                    source_str,
                    " ".join(card.tags),
                ],
                tags=card.tags,
                guid=card.card_id,
            )
        else:
            note = genanki.Note(
                model=_BASIC_MODEL,
                fields=[
                    card.front,
                    card.back,
                    card.explanation or "",
                    card.mnemonic or "",
                    source_str,
                    " ".join(card.tags),
                ],
                tags=card.tags,
                guid=card.card_id,
            )
        deck.add_note(note)

    package = genanki.Package(deck)
    package.write_to_file(str(output_path))
    return output_path


# ---------- markdown study guide --------------------------------------------


def export_markdown_guide(guide: StudyGuide, output_path: Path) -> Path:
    """Render the StudyGuide as a single Markdown document.

    Mermaid blocks render natively in Obsidian, GitHub, and most Markdown
    viewers — so the guide drops back into your vault as a usable note.
    """
    output_path = output_path.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    lines.append(f"# {guide.exam_name}")
    lines.append("")
    lines.append(f"*Matéria: {guide.subject} · Gerado em {guide.generated_at.strftime('%Y-%m-%d %H:%M')} · Idioma: {guide.language}*")
    lines.append("")

    if guide.high_yield_summary:
        lines.append("## Resumo de alto rendimento para o dia da prova")
        lines.append("")
        lines.append(guide.high_yield_summary)
        lines.append("")
        lines.append("---")
        lines.append("")

    lines.append("## Índice")
    lines.append("")
    for i, s in enumerate(guide.sections, start=1):
        slug = _slugify(s.heading)
        lines.append(f"{i}. [{s.heading}](#{slug})")
    lines.append("")
    lines.append("---")
    lines.append("")

    for s in guide.sections:
        lines.append(f"## {s.heading}")
        lines.append("")
        lines.append(s.summary)
        lines.append("")
        if s.key_points:
            lines.append("### Pontos-chave")
            lines.append("")
            for kp in s.key_points:
                lines.append(f"- {kp}")
            lines.append("")
        if s.comparison_table_md:
            lines.append("### Comparação")
            lines.append("")
            lines.append(s.comparison_table_md)
            lines.append("")
        if s.flowchart_mermaid:
            lines.append("### Fluxo / via metabólica")
            lines.append("")
            lines.append("```mermaid")
            lines.append(s.flowchart_mermaid)
            lines.append("```")
            lines.append("")
        if s.mnemonic:
            lines.append(f"> **Mnemônico:** {s.mnemonic}")
            lines.append("")
        if s.source_chunks:
            lines.append(f"<sub>Fontes: {', '.join(s.source_chunks)}</sub>")
            lines.append("")
        lines.append("---")
        lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def _slugify(s: str) -> str:
    return "".join(c.lower() if c.isalnum() else "-" for c in s).strip("-")
