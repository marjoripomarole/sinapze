"""Build a self-contained static HTML file for GitHub Pages.

Usage:
    python build_static.py              # outputs docs/index.html
    python build_static.py --exam N1    # single exam only
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

OUT_DIR = Path(__file__).parent / "out"
DATA_DIR = Path(__file__).parent / ".medstudy"
DOCS_DIR = Path(__file__).parent / "docs"


def load_exam_data(name: str) -> dict:
    guide = ""
    g = OUT_DIR / f"{name}_guide.md"
    if g.exists():
        guide = g.read_text(encoding="utf-8")

    plan = ""
    for suffix in ("_plano_revisao.md", "_cram_plan.md"):
        p = OUT_DIR / f"{name}{suffix}"
        if p.exists():
            plan = p.read_text(encoding="utf-8")
            break

    cards: list = []
    c = DATA_DIR / f"cards__{name}.json"
    if c.exists():
        cards = json.loads(c.read_text(encoding="utf-8")).get("cards", [])

    apkg_exists = (OUT_DIR / f"{name}.apkg").exists()

    return {
        "name": name,
        "guide": guide,
        "cards": cards,
        "has_guide": bool(guide),
        "has_cards": bool(cards),
        "card_count": len(cards),
        "apkg_url": f"{name}.apkg" if apkg_exists else None,
    }


def build(exam_filter: str | None = None) -> Path:
    # Import HTML template from web.py
    sys.path.insert(0, str(Path(__file__).parent))
    from web import HTML

    scope_files = sorted(DATA_DIR.glob("scope__*.json"))
    if not scope_files:
        print("Nenhum scope encontrado. Rode medstudy ingest + scope primeiro.")
        sys.exit(1)

    exams = []
    for sf in scope_files:
        name = sf.stem.replace("scope__", "")
        if exam_filter and name != exam_filter:
            continue
        print(f"  carregando {name}…")
        exams.append(load_exam_data(name))

    if not exams:
        print(f"Exam '{exam_filter}' não encontrado.")
        sys.exit(1)

    payload = json.dumps({"exams": exams}, ensure_ascii=False)
    injection = f"<script>window.__STATIC__ = {payload};</script>"

    # Inject just before the first <script> tag in the HTML body
    static_html = HTML.replace(
        "<script>\n// Static data injected by build_static.py",
        f"{injection}\n<script>\n// Static data injected by build_static.py",
        1,
    )

    DOCS_DIR.mkdir(exist_ok=True)
    out = DOCS_DIR / "index.html"
    out.write_text(static_html, encoding="utf-8")

    # copy .apkg files so the download link works on GitHub Pages
    for e in exams:
        apkg_src = OUT_DIR / f"{e['name']}.apkg"
        if apkg_src.exists():
            shutil.copy2(apkg_src, DOCS_DIR / apkg_src.name)
            print(f"  copiado {apkg_src.name} → docs/")

    size_kb = out.stat().st_size // 1024
    print(f"\nSite estático gerado → {out}  ({size_kb} KB)")
    print("Para publicar no GitHub Pages:")
    print("  git add docs/ && git commit -m 'build static site'")
    print("  git push")
    print("  → Settings → Pages → Source: main / docs/")
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--exam", default=None, help="Incluir apenas este exam")
    args = parser.parse_args()
    build(args.exam)
