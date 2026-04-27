"""End-to-end example using the Python API instead of the CLI.

Run this from the project root after `pip install -e .` and setting your
ANTHROPIC_API_KEY in .env.
"""

from pathlib import Path

from sinapze import (
    export_anki_deck,
    export_markdown_guide,
    generate_cards,
    generate_study_guide,
    ingest_directory,
)
from sinapze.ingest import auto_scope_from_sources, save_scope


def main() -> None:
    # 1. Ingest a directory (sync your Google Drive folder locally first)
    source_dir = Path("~/GoogleDrive/MedSchool/MoleculaACelula").expanduser()
    sources, chunks = ingest_directory(source_dir)
    print(f"Ingested {len(sources)} files, {len(chunks)} chunks")

    # 2. Define exam scope — here, all ingested sources
    exam_name = "molecula_a_celula_prova1"
    scope = auto_scope_from_sources(exam_name, sources)
    save_scope(scope)

    # 3. Generate a study guide first (do this tonight)
    course_description = (
        "Abordagem integrada sobre como as biomoléculas constroem e impactam "
        "a biologia humana. pH, tampões, macromoléculas (carboidratos, proteínas, "
        "lipídeos, ácidos nucleicos), enzimas, membranas celulares, transporte, "
        "compartimentalização, organelas, citoesqueleto, núcleo, cromatina, "
        "ciclo celular, divisão celular, expressão gênica (transcrição, tradução)."
    )
    guide = generate_study_guide(
        chunks,
        exam_name=exam_name,
        subject="biochemistry",
        course_description=course_description,
    )
    guide_path = export_markdown_guide(guide, Path("./out/guide.md"))
    print(f"Guide → {guide_path}")

    # 4. Generate Anki cards (do this tomorrow)
    cards = generate_cards(
        chunks,
        exam_name=exam_name,
        subject="biochemistry",
    )
    deck_path = export_anki_deck(
        cards,
        Path("./out/molecula_a_celula_prova1.apkg"),
        deck_name="Molécula a Célula — Prova 1",
    )
    print(f"Deck ({len(cards)} cards) → {deck_path}")


if __name__ == "__main__":
    main()
