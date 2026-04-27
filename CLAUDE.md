# sinapze — project context for Claude Code

You are working on `sinapze`, a source-grounded study-material generator for
medical school. It ingests PDFs and Obsidian markdown notes, generates a
synthesis-focused study guide and an Anki `.apkg` deck, emits a 24-hour cram
schedule, and serves everything through a local web UI. The pipeline is
grounded in cognitive-science research (Wozniak, Matuschak, Roediger &
Karpicke, Dunlosky 2013, Brown Alpert Med 2025).

GitHub repo: https://github.com/marjoripomarole/sinapze
GitHub Pages: https://marjoripomarole.github.io/sinapze/

## Working directory

All commands are run from `medstudy/` (the extracted package root):

```bash
cd /Users/marjoripomarole/projects/medstudy/medstudy
.venv/bin/sinapze <command>
python web.py          # web UI on http://localhost:8000
```

## Architecture

CLI tool + FastAPI web UI, Python 3.13, ~2 200 lines. Modules:

| Module | Responsibility |
|---|---|
| `sinapze/models.py` | Pydantic models: Source, Chunk, Fact, Card, StudyGuide, Scope |
| `sinapze/config.py` | pydantic-settings; loads from `.env` and `MEDSTUDY_*` env vars |
| `sinapze/ingest.py` | PDF (pypdf) + markdown (frontmatter) parsing, semantic chunking |
| `sinapze/scope.py` | Frontmatter-driven exam scoping + source ranking |
| `sinapze/prompts.py` | Master prompts encoding cognitive-science principles |
| `sinapze/llm.py` | Anthropic SDK wrapper with rate-limit-aware retry logic |
| `sinapze/generate.py` | Three-pass pipeline: extract facts → cardify → verify; map-reduce guide |
| `sinapze/export.py` | `.apkg` (genanki) + markdown study guide |
| `sinapze/plan.py` | 24-hour 6-pass cram schedule (en + pt-BR) |
| `sinapze/cli.py` | Click commands: ingest, scope, scope-from-tags, rank, guide, cards, plan, doctor |
| `web.py` | FastAPI web UI — guide and card quiz (root of project, not inside package) |

## Core design philosophy — DO NOT VIOLATE

1. **Source-grounded.** Every fact, card, and guide section must cite a
   verbatim `source_span` ≤25 words from the input. The verifier pass
   rejects cards whose source span doesn't entail the back. Hallucinations
   in medical content are unacceptable.
2. **Atomic cards (Wozniak).** One fact per card. Cloze by default.
   Basic Q/A only for "why?" prompts. No yes/no cards. No list cards.
3. **Active recall (Roediger).** Stems must not leak the answer.
   Generate elaborative-interrogation companion cards for mechanisms.
   Generate discrimination cards for similar items (drugs in a class).
4. **Language: always pt-BR.** The user is Brazilian. All generated output
   (guide, cards, plan) must be in Portuguese regardless of source language.
   The `GUIDE_SYSTEM` prompt has an explicit override for this.
5. **Strict JSON from the LLM.** Pydantic validates everything. Drop
   malformed items silently, never paper over them.

## Rate-limit constraints (Tier 1 API)

The API key is on Anthropic Tier 1: **30 000 input tokens/minute**.

- Guide generation uses map-reduce: 80 K char batches (~20 K tokens each)
  with a mandatory 65-second sleep between batches. Expect ~30 min for a
  677-chunk corpus.
- `llm.py` has two retry layers: fast exponential for transient errors,
  fixed 65-second wait for `RateLimitError`.
- Cards extraction (`extract_facts`) calls the API once per chunk — with
  677 chunks this takes ~45 min end-to-end.

## Multi-source ingest

`sinapze ingest` accepts multiple `--source` flags. It calls
`ingest_directory(persist=False)` for each and persists once at the end:

```bash
.venv/bin/sinapze ingest \
  --source "/path/to/obsidian/notes" \
  --source "/path/to/professor/pdfs"
```

## Cards → web UI

After `sinapze cards` finishes it saves two outputs:
- `out/<exam>.apkg` — import into Anki
- `.sinapze/cards__<exam>.json` — read by the web UI's card quiz tab

## Web UI (`web.py`)

FastAPI + inline HTML (Alpine.js + Tailwind CDN, no build step).

```bash
python web.py          # starts on port 8000 with --reload
```

Two tabs: **Guia de Estudos**, **Cartões** (flip cards, Sabia/Difícil rating).
Light/dark toggle in the header — preference persisted in localStorage.
Supports multiple exams via a dropdown (auto-detected from `.sinapze/`).
KaTeX renders LaTeX math formulas in the guide and cards.

## Static site (GitHub Pages)

```bash
.venv/bin/python build_static.py   # generates docs/index.html + copies .apkg
git add docs/ && git commit && git push
```

Data embedded as `window.__STATIC__` JSON. Web UI checks this before fetch.

## Current exam

- Exam name: **N1**, subject: Molécula à Célula I (bioquímica e biologia celular)
- Exam date: 2026-04-28T09:00
- 135 sources scoped (177 ingested, noise filtered)
- Guide: complete at `out/N1_guide.md` (5507 lines, 518 KB)
- Cards: complete at `out/N1.apkg` (400 cards); `.sinapze/cards__N1.json`
- Cram plan: complete at `out/N1_plano_revisao.md`

## Deferred features — DO NOT ADD without discussion

- Obsidian plugin as primary UI
- Local vector store (SQLite+vec1, pgvector)
- In-app FSRS scheduler
- Tiered local + hosted model architecture
- PubMed cross-checking
- HIPAA / PHI screening

## Coding conventions

- Type hints everywhere; `X | None` not `Optional[X]`
- `from __future__ import annotations` at the top of every module
- Pydantic v2 syntax (`model_dump_json`, `model_validate_json`, `Field`)
- Click for CLI, Rich for output, FastAPI for web
- Tenacity for LLM retry logic
- Prefer pure functions; side effects in narrow layers

## Common commands

```bash
.venv/bin/sinapze doctor                                      # validate config
.venv/bin/sinapze ingest --source <dir> [--source <dir2>]    # parse sources
.venv/bin/sinapze scope --exam <name> [--exclude <kw>]       # define scope
.venv/bin/sinapze scope-from-tags --exam <name>              # scope from frontmatter
.venv/bin/sinapze rank                                        # show source ranking
.venv/bin/sinapze guide --exam <n> --output <p>              # study guide (~30 min)
.venv/bin/sinapze cards --exam <n> --output <p>              # Anki deck (~45 min)
.venv/bin/sinapze plan --exam <n> --exam-datetime <iso> --lang pt-BR
python web.py                                                 # web UI on :8000
python build_static.py                                        # build GitHub Pages
```

## Where to start when extending

- **Better extraction:** edit `sinapze/prompts.py` — highest-leverage surface
- **New input type (e.g., .pptx):** add a reader in `sinapze/ingest.py`
- **New output format (e.g., Quizlet TSV):** add a function in `sinapze/export.py`
- **Web UI changes:** edit the `HTML` raw string in `web.py`

## Testing

No tests yet. When adding: use `pytest`, mock `LLMClient.complete_json`,
put fixture chunks/sources in `tests/fixtures/`.
