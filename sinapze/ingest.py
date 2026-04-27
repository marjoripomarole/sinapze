"""Ingest PDFs and Obsidian markdown notes into source-grounded chunks."""

from __future__ import annotations

import json
import re
from pathlib import Path

import frontmatter
from pypdf import PdfReader

from sinapze.config import Settings, get_settings
from sinapze.models import Chunk, Scope, Source

# ---------- file readers ----------------------------------------------------


def _read_pdf(path: Path) -> Source:
    """Extract text from a PDF, preserving page boundaries with a marker."""
    reader = PdfReader(str(path))
    pages = []
    for i, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        pages.append(f"\n[[PAGE_{i}]]\n{text}")
    full_text = "\n".join(pages)
    return Source(
        path=path,
        kind="pdf",
        title=path.stem,
        text=full_text,
        page_count=len(reader.pages),
        word_count=len(full_text.split()),
        language=_guess_language(full_text),
    )


def _read_markdown(path: Path) -> Source:
    """Read an Obsidian markdown note. Preserves frontmatter for scope/ranking."""
    raw = path.read_text(encoding="utf-8")
    post = frontmatter.loads(raw)
    title = post.metadata.get("title", path.stem)
    text = post.content
    return Source(
        path=path,
        kind="markdown",
        title=str(title),
        text=text,
        word_count=len(text.split()),
        language=_guess_language(text),
        frontmatter=dict(post.metadata),
    )


def _guess_language(text: str) -> str:
    """Cheap heuristic: count Portuguese-distinctive tokens vs English."""
    sample = text[:5000].lower()
    pt_markers = sum(sample.count(w) for w in (" é ", " são ", " ção", " não ", " que ", "ção"))
    en_markers = sum(sample.count(w) for w in (" the ", " and ", " is ", " of ", " are "))
    if pt_markers > en_markers:
        return "pt-BR"
    return "en"


# ---------- chunking --------------------------------------------------------


_PARA_SPLIT = re.compile(r"\n\s*\n")
_HEADING = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


def _chunk_text(source: Source, settings: Settings) -> list[Chunk]:
    """Semantic chunking: prefer breaks at headings, then paragraphs.

    Falls back to character windows for unstructured PDF text. Each chunk
    keeps a `page_range` if PAGE markers are present.
    """
    target = settings.chunk_size_chars
    overlap = settings.chunk_overlap_chars
    text = source.text

    # 1. Try to split on headings (works great for markdown, sometimes PDFs)
    heading_positions = [m.start() for m in _HEADING.finditer(text)]
    sections: list[str]
    if heading_positions and source.kind == "markdown":
        sections = _split_at_positions(text, heading_positions)
    else:
        # 2. Fallback: paragraph-greedy packing into ~target-sized blocks
        sections = _greedy_pack(_PARA_SPLIT.split(text), target)

    # 3. If any section is much larger than target, sliding-window split it
    final: list[str] = []
    for s in sections:
        if len(s) <= target * 1.5:
            final.append(s)
        else:
            final.extend(_sliding_window(s, target, overlap))

    chunks: list[Chunk] = []
    for i, body in enumerate(final):
        if not body.strip():
            continue
        page_range = _extract_page_range(body) if source.kind == "pdf" else None
        clean = _strip_page_markers(body)
        chunks.append(
            Chunk(
                source_id=source.source_id,
                source_title=source.title,
                source_path=source.path,
                chunk_index=i,
                text=clean,
                page_range=page_range,
            )
        )
    return chunks


def _split_at_positions(text: str, positions: list[int]) -> list[str]:
    parts: list[str] = []
    bounds = positions + [len(text)]
    prev = 0
    for b in bounds:
        if b > prev:
            parts.append(text[prev:b])
            prev = b
    return parts


def _greedy_pack(paragraphs: list[str], target: int) -> list[str]:
    out: list[str] = []
    buf: list[str] = []
    size = 0
    for p in paragraphs:
        if size + len(p) > target and buf:
            out.append("\n\n".join(buf))
            buf = [p]
            size = len(p)
        else:
            buf.append(p)
            size += len(p) + 2
    if buf:
        out.append("\n\n".join(buf))
    return out


def _sliding_window(text: str, size: int, overlap: int) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(text):
        out.append(text[i : i + size])
        i += size - overlap
    return out


_PAGE_MARK = re.compile(r"\[\[PAGE_(\d+)\]\]")


def _extract_page_range(text: str) -> tuple[int, int] | None:
    nums = [int(m.group(1)) for m in _PAGE_MARK.finditer(text)]
    return (min(nums), max(nums)) if nums else None


def _strip_page_markers(text: str) -> str:
    return _PAGE_MARK.sub("", text).strip()


# ---------- public API ------------------------------------------------------


def ingest_directory(
    source_dir: Path,
    *,
    glob_patterns: tuple[str, ...] = ("**/*.pdf", "**/*.md"),
    settings: Settings | None = None,
    persist: bool = True,
) -> tuple[list[Source], list[Chunk]]:
    """Walk a directory and produce sources + chunks.

    Use this for a synced Google Drive folder, an Obsidian vault, or any
    local tree. Returns sources (one per file) and chunks (many per file).
    Set persist=False when combining multiple directories before saving.
    """
    settings = settings or get_settings()
    source_dir = source_dir.expanduser().resolve()
    if not source_dir.is_dir():
        raise FileNotFoundError(source_dir)

    sources: list[Source] = []
    for pattern in glob_patterns:
        for path in sorted(source_dir.glob(pattern)):
            if path.is_file():
                try:
                    if path.suffix.lower() == ".pdf":
                        sources.append(_read_pdf(path))
                    elif path.suffix.lower() in (".md", ".markdown"):
                        sources.append(_read_markdown(path))
                except Exception as e:  # noqa: BLE001
                    print(f"[warn] failed to read {path}: {e}")

    chunks: list[Chunk] = []
    for src in sources:
        chunks.extend(_chunk_text(src, settings))

    if persist:
        _persist(settings.data_dir, sources, chunks)
    return sources, chunks


def _persist(data_dir: Path, sources: list[Source], chunks: list[Chunk]) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "sources.jsonl").write_text(
        "\n".join(s.model_dump_json() for s in sources), encoding="utf-8"
    )
    (data_dir / "chunks.jsonl").write_text(
        "\n".join(c.model_dump_json() for c in chunks), encoding="utf-8"
    )


def load_persisted(
    data_dir: Path | None = None,
) -> tuple[list[Source], list[Chunk]]:
    """Reload the most recent ingest output."""
    settings = get_settings()
    data_dir = data_dir or settings.data_dir
    sources_file = data_dir / "sources.jsonl"
    chunks_file = data_dir / "chunks.jsonl"
    if not sources_file.exists():
        raise FileNotFoundError(
            f"No ingest data at {data_dir}. Run `sinapze ingest` first."
        )
    sources = [Source.model_validate_json(line) for line in sources_file.read_text("utf-8").splitlines() if line]
    chunks = [Chunk.model_validate_json(line) for line in chunks_file.read_text("utf-8").splitlines() if line]
    return sources, chunks


# ---------- scope (which sources cover which exam) -------------------------


def save_scope(scope: Scope, data_dir: Path | None = None) -> Path:
    """Save the exam scope so guide/cards commands can re-use it."""
    settings = get_settings()
    data_dir = data_dir or settings.data_dir
    data_dir.mkdir(parents=True, exist_ok=True)
    out = data_dir / f"scope__{scope.exam_name}.json"
    out.write_text(scope.model_dump_json(indent=2), encoding="utf-8")
    return out


def load_scope(exam_name: str, data_dir: Path | None = None) -> Scope:
    settings = get_settings()
    data_dir = data_dir or settings.data_dir
    path = data_dir / f"scope__{exam_name}.json"
    if not path.exists():
        raise FileNotFoundError(f"No scope for exam {exam_name!r} at {path}")
    return Scope.model_validate_json(path.read_text("utf-8"))


def auto_scope_from_sources(
    exam_name: str,
    sources: list[Source],
    keyword: str | None = None,
) -> Scope:
    """Auto-build a scope from all ingested sources, optionally filtered by keyword."""
    if keyword:
        kw = keyword.lower()
        matched = [s for s in sources if kw in s.title.lower() or kw in s.text[:5000].lower()]
    else:
        matched = sources
    return Scope(exam_name=exam_name, source_ids=[s.source_id for s in matched])
