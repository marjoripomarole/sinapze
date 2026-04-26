"""medstudy — source-grounded study material generator."""

from medstudy.config import Settings
from medstudy.models import Card, Chunk, Source, StudyGuide
from medstudy.ingest import ingest_directory, load_scope
from medstudy.generate import generate_study_guide, generate_cards
from medstudy.export import export_anki_deck, export_markdown_guide
from medstudy.scope import scope_from_frontmatter, rank_sources, explain_ranking
from medstudy.plan import generate_cram_plan

__version__ = "0.2.0"

__all__ = [
    "Settings",
    "Card",
    "Chunk",
    "Source",
    "StudyGuide",
    "ingest_directory",
    "load_scope",
    "generate_study_guide",
    "generate_cards",
    "export_anki_deck",
    "export_markdown_guide",
    "scope_from_frontmatter",
    "rank_sources",
    "explain_ranking",
    "generate_cram_plan",
]
