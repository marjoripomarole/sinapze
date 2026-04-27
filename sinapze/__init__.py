"""sinapze — source-grounded study material generator."""

from sinapze.config import Settings
from sinapze.models import Card, Chunk, Source, StudyGuide
from sinapze.ingest import ingest_directory, load_scope
from sinapze.generate import generate_study_guide, generate_cards
from sinapze.export import export_anki_deck, export_markdown_guide
from sinapze.scope import scope_from_frontmatter, rank_sources, explain_ranking
from sinapze.plan import generate_cram_plan

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
