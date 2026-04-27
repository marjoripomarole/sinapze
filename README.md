# sinapze

A source-grounded study-material generator for medical school. Reads your
PDFs and Obsidian notes, produces a study guide and Anki deck (`.apkg`)
using a two-pass extract-then-generate pipeline with a hallucination
verifier — built on the cognitive-science evidence summarized in the
project's research report.

## Why this exists

Default LLM flashcards are bad: vague stems, multi-fact backs, hallucinated
medical claims. The Brown Alpert Medical School deployment (medRxiv 2025)
showed that **prompt engineering + source grounding + a verifier pass**
brings hallucination rates to ~1 per 21 cards and produces decks rated
equivalent to faculty material. This project operationalizes that pipeline.

## Pipeline

```
  Sources (PDFs + Obsidian .md)
            │
            ▼
       INGEST  ─── pypdf, python-frontmatter
       parse → semantic chunks with source spans
            │
            ▼
        SCOPE  ─── you tag which files cover which exam
            │
            ▼
   ┌────────┴────────┐
   ▼                 ▼
GENERATE         GENERATE
study guide      flashcards
   │                 │
   │            VERIFIER PASS  ─── reject cards not entailed by source
   │                 │
   ▼                 ▼
guide.md         exam.apkg
```

Each card carries a verbatim `source_span` (≤25 words). The verifier asks
the LLM, for every card, "does this span entail this back? yes/no", and
drops the no's. This is the single biggest hallucination reduction in the
Nature 2025 clinical-summarization work.

## Design principles encoded in the prompts

- **Minimum Information Principle** (Wozniak): one atomic fact per card
- **Active recall + generation** (Roediger & Karpicke 2006): never reveal answer in question
- **Cloze-default** (AnKing convention): cloze for embedded facts, basic Q/A for "why?"
- **Discrimination cards** (Wozniak Rule 11): for similar items in a group
- **Elaborative interrogation** (Pressley 1987): paired "why?" companion cards
- **Image occlusion**: for any labeled diagram (anatomy, pathways, histology)
- **Source-grounding**: only facts in the input; reject unsupported claims
- **Language-aware**: detects source language and matches output (pt-BR safe)

## Quick start

```bash
# 1. install
pip install -e .

# 2. set API key
cp .env.example .env
# edit .env → ANTHROPIC_API_KEY=sk-ant-...

# 3. point it at your materials
sinapze ingest --source ~/GoogleDrive/MedSchool/MoleculaACelula

# 4. define exam scope — TWO options
#    (a) frontmatter-driven (recommended): tag your Obsidian notes
sinapze scope-from-tags --exam prova1
#    (b) keyword-driven (works without tagging)
sinapze scope --exam prova1 --include "molecula" --exclude "draft"

# 5. study guide first (do this tonight)
sinapze guide --exam prova1 --output ./out/guide.md \
  --course-description "biomoléculas, pH, enzimas, membranas, ciclo celular"

# 6. Anki cards (do this tomorrow morning)
sinapze cards --exam prova1 --output ./out/prova1.apkg --max-cards 300

# 7. cram schedule (printout you can follow over 24h)
sinapze plan --exam prova1 --exam-datetime 2026-04-28T09:00 --lang pt-BR \
  --output ./out/cram_plan.md
```

## Frontmatter scoping (v0.2)

Tag your Obsidian notes once and `scope-from-tags` reads them automatically:

```yaml
---
exam: prova1               # or [prova1, prova2] for multi-exam coverage
course: molecula_a_celula
high_yield: true
exam_weight: 0.9           # 0.0–1.0, used to rank when --max-cards bites
objectives: [glycolysis, krebs, etmc]
---

# Glycolysis

...your note content...
```

Sources are then ranked by `exam_weight × high_yield × word_count`, so
when the deck cap forces a trim, low-priority material drops first.
Run `sinapze rank` to see the current ranking.

## The 24-hour cram plan (v0.2)

Anki schedules cards but doesn't tell you *when* to study. The `plan`
command emits a 6-pass markdown checklist anchored to your exam time:

- Pass A (T-24h): diagnostic — read the high-yield summary, flag weak sections
- Pass B (T-23h): failed-recall sweep — filtered deck on flagged tags
- Pass C (T-20h): deep dive on weakest topic, build a comparison table from memory
- Pass D (T-14h): mixed retrieval, ~150 cards interleaved
- Pass E (T-10h): pre-sleep weak set — exploits overnight consolidation
- Pass F (T-2h):  morning final pass + one coffee, no new material

Why 6 passes: at least two retrievals beat one exposure (Cepeda 2008),
sleep consolidates declarative memory (Walker, Gais 2006), and rescheduling
is OFF in the filtered decks so cramming doesn't corrupt long-term intervals.

## Architecture decisions

### Why no vector DB in v1
For a single exam (5–15 lectures, ~50–150 KB of text) everything fits in
Claude's 200K context. Retrieval-augmented generation adds complexity and
removes context that helps disambiguate cross-references. Add Chroma/Qdrant
in v2 when your library grows past a few MB.

### Why Claude (default) and not GPT-4
Both work — there's a thin `LLMClient` abstraction. Claude's defaults
(higher token limits, lower hallucination on long-context summarization in
the Nature 2025 benchmarks, native `tool_use` for structured output) make
it the better default for medical content. Swap by changing
`SINAPZE_LLM_PROVIDER`.

### Why two passes (extract → cardify) instead of one
One-pass card generation conflates two reasoning steps and the model often
skips facts to keep cards looking clean. Extract-then-cardify produces
≥30% more atomic cards on the same source (Brown 2025).

## Roadmap

- [x] **v0.1**: PDF + markdown ingest, study guide, Anki export, verifier pass
- [x] **v0.2**: YAML frontmatter scoping, source ranking, 24h cram plan (pt-BR + en)
- [ ] v0.3: Image occlusion auto-generation from labeled figures
- [ ] v0.4: Vector retrieval for libraries >5MB
- [ ] v0.5: FastAPI + React web UI
- [ ] v0.6: Direct Google Drive integration (currently use Drive desktop sync)
- [ ] v0.7: FSRS retention prediction + adaptive card density

## Intentionally NOT on the roadmap

After reviewing alternative architectures (incl. a strategy doc proposing
an Obsidian-plugin-first stack), some popular ideas were considered and
deferred:

- **Obsidian plugin as primary UI.** TypeScript + Obsidian API + React UI
  + IPC to Python is 3 runtimes for an MVP. CLI ships now; plugin is a
  legitimate v1 feature once the engine stabilizes.
- **Local vector store from day 1 (SQLite+vec1, pgvector).** Premature for
  single-exam scope; full-context generation beats top-k retrieval for
  cross-reference resolution. Adds when your library passes ~5MB.
- **In-app FSRS scheduler.** Anki already does this. Exporting `.apkg`
  is the right division of labor.
- **Tiered local + hosted model architecture.** Genuine value at scale,
  overkill for personal use; one strong model handles all four jobs.
- **PubMed cross-checking.** Useful for board prep against published
  evidence, less useful when the exam is from professor-specific slides.
- **HIPAA / PHI screening.** Personal study notes aren't PHI; regulatory
  framing is misplaced. Keep a privacy-conscious default (local files,
  explicit opt-in for any external service) without compliance theater.
