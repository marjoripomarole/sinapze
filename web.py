"""Simple web interface for medstudy output files.

Run:  python web.py
Then open: http://localhost:8000
"""

from __future__ import annotations

import json
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

app = FastAPI(title="medstudy")

OUT_DIR = Path(__file__).parent / "out"
DATA_DIR = Path(__file__).parent / ".medstudy"


# ---------- API ---------------------------------------------------------------

@app.get("/api/exams")
def list_exams() -> JSONResponse:
    exams = []
    for scope_file in sorted(DATA_DIR.glob("scope__*.json")):
        name = scope_file.stem.replace("scope__", "")
        guide = OUT_DIR / f"{name}_guide.md"
        plan_pt = OUT_DIR / f"{name}_plano_revisao.md"
        plan_en = OUT_DIR / f"{name}_cram_plan.md"
        cards_file = DATA_DIR / f"cards__{name}.json"
        exams.append({
            "name": name,
            "has_guide": guide.exists(),
            "has_plan": plan_pt.exists() or plan_en.exists(),
            "has_cards": cards_file.exists(),
            "card_count": len(json.loads(cards_file.read_text())["cards"]) if cards_file.exists() else 0,
        })
    return JSONResponse(exams)


@app.get("/api/exam/{name}/guide")
def get_guide(name: str) -> JSONResponse:
    p = OUT_DIR / f"{name}_guide.md"
    if not p.exists():
        raise HTTPException(404, "Guide not generated yet. Run: medstudy guide --exam " + name)
    return JSONResponse({"content": p.read_text(encoding="utf-8")})


@app.get("/api/exam/{name}/plan")
def get_plan(name: str) -> JSONResponse:
    for suffix in ("_plano_revisao.md", "_cram_plan.md"):
        p = OUT_DIR / f"{name}{suffix}"
        if p.exists():
            return JSONResponse({"content": p.read_text(encoding="utf-8")})
    raise HTTPException(404, "Plan not generated yet. Run: medstudy plan --exam " + name)


@app.get("/api/exam/{name}/cards")
def get_cards(name: str) -> JSONResponse:
    p = DATA_DIR / f"cards__{name}.json"
    if not p.exists():
        raise HTTPException(404, "Cards not generated yet. Run: medstudy cards --exam " + name)
    return JSONResponse(json.loads(p.read_text(encoding="utf-8")))


# ---------- Frontend ----------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(HTML)


HTML = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>medstudy</title>
<script src="https://cdn.tailwindcss.com"></script>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
<script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3/dist/cdn.min.js"></script>
<style>
  /* ── CSS variables — dark (default) ── */
  :root {
    --bg:        #020617;
    --bg2:       #0f172a;
    --surface:   #1e293b;
    --surface2:  #334155;
    --border:    #334155;
    --text:      #e2e8f0;
    --text2:     #94a3b8;
    --text3:     #64748b;
    --accent:    #38bdf8;
    --accent2:   #0369a1;
    --head-bg:   #0f172a;
    --code-fg:   #f472b6;
    --even-row:  #0a0f1e;
    --card-back: #020617;
  }
  /* ── light overrides ── */
  .light {
    --bg:        #f8fafc;
    --bg2:       #f1f5f9;
    --surface:   #ffffff;
    --surface2:  #e2e8f0;
    --border:    #cbd5e1;
    --text:      #0f172a;
    --text2:     #475569;
    --text3:     #94a3b8;
    --accent:    #0284c7;
    --accent2:   #0369a1;
    --head-bg:   #ffffff;
    --code-fg:   #db2777;
    --even-row:  #f8fafc;
    --card-back: #f0f9ff;
  }

  [x-cloak] { display:none !important; }
  body { background:var(--bg); color:var(--text); transition:background .2s,color .2s; }

  /* header / nav */
  .app-header { background:var(--head-bg); border-bottom:1px solid var(--border); }
  .tab-btn    { color:var(--text2); }
  .tab-btn:hover { background:var(--surface); color:var(--text); }
  .tab-active { background:#0284c7; color:#fff !important; }
  .exam-select { background:var(--surface); border:1px solid var(--border); color:var(--text); }

  /* prose */
  .prose { color:var(--text); }
  .prose h1 { font-size:1.7rem; font-weight:700; margin:1.4rem 0 .5rem; border-bottom:2px solid var(--border); padding-bottom:.3rem; color:var(--text); }
  .prose h2 { font-size:1.35rem; font-weight:700; margin:1.2rem 0 .4rem; color:var(--accent); }
  .prose h3 { font-size:1.1rem; font-weight:600; margin:1rem 0 .3rem; color:var(--text2); }
  .prose p  { margin:.6rem 0; line-height:1.75; }
  .prose ul { list-style:disc; padding-left:1.5rem; margin:.5rem 0; }
  .prose ol { list-style:decimal; padding-left:1.5rem; margin:.5rem 0; }
  .prose li { margin:.25rem 0; line-height:1.65; }
  .prose table { width:100%; border-collapse:collapse; margin:1rem 0; font-size:.9rem; }
  .prose th { background:var(--surface); padding:.5rem .75rem; text-align:left; border:1px solid var(--border); color:var(--accent); }
  .prose td { padding:.45rem .75rem; border:1px solid var(--border); }
  .prose tr:nth-child(even) td { background:var(--even-row); }
  .prose code { background:var(--surface); padding:.1rem .35rem; border-radius:.25rem; font-size:.85em; color:var(--code-fg); }
  .prose pre  { background:var(--surface); padding:1rem; border-radius:.5rem; overflow-x:auto; margin:.75rem 0; }
  .prose pre code { background:none; padding:0; color:var(--text); }
  .prose blockquote { border-left:3px solid var(--accent); padding-left:1rem; color:var(--text2); margin:.75rem 0; }
  .prose hr  { border-color:var(--border); margin:1.5rem 0; }

  /* panels */
  .panel   { background:var(--surface); border:1px solid var(--border); }
  .panel2  { background:var(--surface2); }
  .muted   { color:var(--text2); }
  .dimmed  { color:var(--text3); }

  /* plan checkboxes */
  .plan-check:checked + label { text-decoration:line-through; color:var(--text3); }

  /* cards */
  .card-front { background:var(--surface);  border:1px solid var(--border); }
  .card-back  { background:var(--card-back); border:1px solid var(--accent); }
  .card-back  { transform:rotateY(180deg); backface-visibility:hidden; -webkit-backface-visibility:hidden; }
  .card-front { backface-visibility:hidden; -webkit-backface-visibility:hidden; }

  /* input */
  .app-input  { background:var(--surface); border:1px solid var(--border); color:var(--text); }
  .app-input::placeholder { color:var(--text3); }
  .app-btn    { background:var(--surface); border:1px solid var(--border); color:var(--text); }
  .app-btn:hover { background:var(--surface2); }

  /* theme toggle */
  .theme-btn { background:var(--surface); border:1px solid var(--border); color:var(--text2); border-radius:.5rem; padding:.3rem .65rem; font-size:.85rem; cursor:pointer; transition:background .15s; }
  .theme-btn:hover { background:var(--surface2); }

  /* mermaid diagrams */
  .mermaid-wrap { background:var(--surface); border:1px solid var(--border); border-radius:.75rem; padding:1.5rem; margin:1rem 0; overflow-x:auto; text-align:center; }
  .mermaid-wrap svg { max-width:100%; height:auto; }
  .mermaid-label { font-size:.7rem; color:var(--text3); text-align:right; margin-top:.5rem; letter-spacing:.03em; }
</style>
</head>
<body class="min-h-screen font-sans" x-data="app()" x-init="init()" :class="light ? 'light' : ''" x-cloak>

<!-- Header -->
<header class="app-header px-6 py-3 flex items-center gap-4 sticky top-0 z-50">
  <span class="font-bold text-sky-500 text-lg tracking-tight">medstudy</span>

  <select x-model="currentExam" @change="switchExam()" class="exam-select text-sm rounded px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-sky-500">
    <template x-for="e in exams" :key="e.name">
      <option :value="e.name" x-text="e.name"></option>
    </template>
  </select>

  <nav class="flex gap-1 ml-4">
    <template x-for="tab in tabs" :key="tab.id">
      <button @click="activeTab = tab.id"
        :class="activeTab === tab.id ? 'tab-active' : 'tab-btn'"
        class="px-4 py-1.5 rounded text-sm font-medium transition-colors">
        <span x-text="tab.label"></span>
        <span x-show="tab.id === 'cards' && exam?.card_count"
          class="ml-1 text-xs bg-sky-100 text-sky-700 px-1.5 py-0.5 rounded-full"
          x-text="exam?.card_count"></span>
      </button>
    </template>
  </nav>

  <div class="ml-auto flex items-center gap-3">
    <span class="text-xs dimmed" x-text="statusMsg"></span>
    <!-- Theme toggle -->
    <button class="theme-btn" @click="toggleTheme()" :title="light ? 'Modo escuro' : 'Modo claro'">
      <span x-text="light ? '🌙 Escuro' : '☀️ Claro'"></span>
    </button>
  </div>
</header>

<!-- Main -->
<main class="max-w-5xl mx-auto px-6 py-8">

  <!-- ── GUIDE ── -->
  <div x-show="activeTab === 'guide'">
    <div x-show="guideLoading" class="muted text-center py-20"><p class="text-lg">Carregando guia…</p></div>
    <div x-show="guideError" class="panel rounded-xl p-8 text-center muted">
      <p class="text-xl mb-2">📄</p>
      <p x-text="guideError"></p>
      <p class="text-sm mt-3 dimmed">O guia está sendo gerado. Atualize a página em alguns minutos.</p>
    </div>
    <div x-show="!guideLoading && !guideError" class="prose" x-html="guideHtml"></div>
  </div>

  <!-- ── PLAN ── -->
  <div x-show="activeTab === 'plan'">
    <div x-show="planLoading" class="muted text-center py-20">Carregando plano…</div>
    <div x-show="planError" class="panel rounded-xl p-8 text-center muted"><p x-text="planError"></p></div>
    <div x-show="!planLoading && !planError" class="prose" x-html="planHtml"></div>
  </div>

  <!-- ── CARDS ── -->
  <div x-show="activeTab === 'cards'">
    <div x-show="!exam || !exam.has_cards" class="panel rounded-xl p-10 text-center muted">
      <p class="text-3xl mb-4">🃏</p>
      <p class="text-lg mb-2">Os cartões ainda não foram gerados.</p>
      <code class="text-sm panel2 px-3 py-1.5 rounded text-sky-600">
        medstudy cards --exam <span x-text="currentExam"></span> --output ./out/<span x-text="currentExam"></span>.apkg
      </code>
    </div>

    <div x-show="exam && exam.has_cards">
      <div class="flex items-center gap-4 mb-6">
        <input x-model="cardSearch" type="search" placeholder="Buscar cartões…"
          class="app-input flex-1 rounded-lg px-4 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-sky-500">
        <span class="text-sm muted"><span x-text="filteredCards.length"></span> cartões</span>
        <button @click="shuffleCards()" class="app-btn text-sm px-3 py-2 rounded-lg transition-colors">Embaralhar</button>
        <button @click="resetProgress()" class="text-sm dimmed hover:text-sky-500 transition-colors">Resetar</button>
      </div>

      <div class="mb-6">
        <div class="flex justify-between text-xs dimmed mb-1">
          <span>Progresso da sessão</span>
          <span x-text="Math.round(sessionProgress * 100) + '%'"></span>
        </div>
        <div class="h-1.5 rounded-full overflow-hidden" style="background:var(--surface2)">
          <div class="h-full bg-sky-500 rounded-full transition-all" :style="`width:${sessionProgress*100}%`"></div>
        </div>
      </div>

      <div x-show="filteredCards.length > 0">
        <div style="perspective:1200px; min-height:280px; position:relative;">
          <template x-if="currentCard">
            <div class="cursor-pointer select-none"
              :style="cardFlipped ? 'transform:rotateY(180deg)' : ''"
              @click="cardFlipped = !cardFlipped"
              style="transform-style:preserve-3d; transition:transform .5s; min-height:280px; position:relative;">

              <div class="card-front absolute inset-0 rounded-2xl p-8 flex flex-col justify-center">
                <div class="text-xs dimmed mb-4 flex gap-2 flex-wrap">
                  <template x-for="tag in currentCard.tags.slice(0,4)" :key="tag">
                    <span class="panel2 px-2 py-0.5 rounded muted" x-text="tag"></span>
                  </template>
                </div>
                <p class="text-lg leading-relaxed" x-text="currentCard.front"></p>
                <p class="text-xs dimmed mt-6 text-center">clique para revelar</p>
              </div>

              <div class="card-back absolute inset-0 rounded-2xl p-8 flex flex-col justify-center">
                <p class="text-base leading-relaxed" x-text="currentCard.back || '(cloze — ver frente)'"></p>
                <div x-show="currentCard.explanation" class="mt-4 text-sm dimmed pt-3" style="border-top:1px solid var(--border)" x-text="currentCard.explanation"></div>
                <div x-show="currentCard.mnemonic" class="mt-3 text-sm text-amber-600 italic" x-text="'💡 ' + currentCard.mnemonic"></div>
                <p class="text-xs dimmed mt-3 pt-3" style="border-top:1px solid var(--border)" x-text="'Fonte: ' + currentCard.source_span"></p>
              </div>
            </div>
          </template>
        </div>

        <div class="flex items-center justify-center gap-6 mt-6">
          <button @click="prevCard()" :disabled="cardIndex === 0"
            class="app-btn px-5 py-2 rounded-lg transition-colors disabled:opacity-30 disabled:cursor-not-allowed">← Anterior</button>

          <div class="flex gap-3">
            <button @click="markCard('hard')"
              class="px-4 py-2 rounded-lg text-sm transition-colors"
              style="background:rgba(239,68,68,.15); color:#ef4444">Difícil</button>
            <button @click="markCard('good')"
              class="px-4 py-2 rounded-lg text-sm transition-colors"
              style="background:rgba(34,197,94,.15); color:#16a34a">Sabia ✓</button>
          </div>

          <button @click="nextCard()" :disabled="cardIndex >= filteredCards.length - 1"
            class="app-btn px-5 py-2 rounded-lg transition-colors disabled:opacity-30 disabled:cursor-not-allowed">Próximo →</button>
        </div>

        <p class="text-center text-xs dimmed mt-3">
          <span x-text="cardIndex + 1"></span> / <span x-text="filteredCards.length"></span>
        </p>
      </div>
    </div>
  </div>

</main>

<script>
marked.setOptions({ breaks: true, gfm: true });

function initMermaid(light) {
  mermaid.initialize({
    startOnLoad: false,
    theme: light ? 'default' : 'dark',
    themeVariables: light
      ? { primaryColor: '#e0f2fe', primaryTextColor: '#0c4a6e', primaryBorderColor: '#7dd3fc',
          lineColor: '#0284c7', background: '#ffffff', mainBkg: '#f0f9ff' }
      : { primaryColor: '#1e3a5f', primaryTextColor: '#e2e8f0', primaryBorderColor: '#38bdf8',
          lineColor: '#38bdf8', background: '#0f172a', mainBkg: '#1e293b' },
    flowchart: { curve: 'basis', padding: 20 },
  });
}

async function renderMermaid() {
  await new Promise(r => setTimeout(r, 50)); // let Alpine flush x-html
  const blocks = document.querySelectorAll('pre code.language-mermaid');
  if (!blocks.length) return;
  blocks.forEach(code => {
    const pre = code.parentElement;
    const src = code.textContent;
    const wrap = document.createElement('div');
    wrap.className = 'mermaid-wrap';
    const diag = document.createElement('div');
    diag.className = 'mermaid';
    diag.textContent = src;
    const lbl = document.createElement('div');
    lbl.className = 'mermaid-label';
    lbl.textContent = 'diagrama gerado automaticamente';
    wrap.appendChild(diag);
    wrap.appendChild(lbl);
    pre.replaceWith(wrap);
  });
  await mermaid.run({ querySelector: '.mermaid' });
}

function app() {
  return {
    exams: [], exam: null, currentExam: '',
    activeTab: 'guide',
    light: localStorage.getItem('theme') === 'light',
    tabs: [
      { id: 'guide', label: 'Guia de Estudos' },
      { id: 'plan',  label: 'Plano de Revisão' },
      { id: 'cards', label: 'Cartões' },
    ],
    guideHtml: '', guideLoading: true, guideError: '',
    planHtml: '',  planLoading: true,  planError: '',
    planChecks: {},
    cards: [], cardIndex: 0, cardFlipped: false, cardSearch: '',
    cardProgress: {}, statusMsg: '',

    get currentCard() { return this.filteredCards[this.cardIndex] || null; },
    get filteredCards() {
      if (!this.cardSearch) return this.cards;
      const q = this.cardSearch.toLowerCase();
      return this.cards.filter(c =>
        c.front.toLowerCase().includes(q) ||
        (c.back||'').toLowerCase().includes(q) ||
        c.tags.some(t => t.toLowerCase().includes(q))
      );
    },
    get sessionProgress() {
      const done = Object.values(this.cardProgress).filter(Boolean).length;
      return this.cards.length ? done / this.cards.length : 0;
    },

    toggleTheme() {
      this.light = !this.light;
      localStorage.setItem('theme', this.light ? 'light' : 'dark');
      initMermaid(this.light);
      renderMermaid();
    },

    async init() {
      initMermaid(this.light);
      const res = await fetch('/api/exams');
      this.exams = await res.json();
      if (this.exams.length) { this.currentExam = this.exams[0].name; await this.switchExam(); }
    },

    async switchExam() {
      this.exam = this.exams.find(e => e.name === this.currentExam) || null;
      this.guideLoading = true; this.guideError = '';
      this.planLoading  = true; this.planError  = '';
      this.cards = []; this.cardIndex = 0;
      this.planChecks   = JSON.parse(localStorage.getItem('planChecks_'   + this.currentExam) || '{}');
      this.cardProgress = JSON.parse(localStorage.getItem('cardProgress_' + this.currentExam) || '{}');
      await Promise.all([this.loadGuide(), this.loadPlan()]);
      if (this.exam?.has_cards) await this.loadCards();
    },

    async loadGuide() {
      try {
        const r = await fetch('/api/exam/' + this.currentExam + '/guide');
        if (!r.ok) { this.guideError = (await r.json()).detail; return; }
        this.guideHtml = marked.parse((await r.json()).content);
        this.statusMsg = 'Guia carregado';
        this.$nextTick(renderMermaid);
      } catch { this.guideError = 'Erro ao carregar guia.'; }
      finally { this.guideLoading = false; }
    },

    async loadPlan() {
      try {
        const r = await fetch('/api/exam/' + this.currentExam + '/plan');
        if (!r.ok) { this.planError = (await r.json()).detail; return; }
        this.planHtml = this.renderPlan((await r.json()).content);
      } catch { this.planError = 'Erro ao carregar plano.'; }
      finally { this.planLoading = false; }
    },

    renderPlan(md) {
      let idx = 0;
      const withChecks = md.replace(/- \[ \] (.+)/g, (_, text) => {
        const id = 'check_' + idx++;
        const checked = this.planChecks[id] ? 'checked' : '';
        return `<div class="flex items-start gap-2 my-2">
          <input type="checkbox" id="${id}" class="plan-check mt-1 accent-sky-500 w-4 h-4 flex-shrink-0" ${checked}
            onchange="window.savePlanCheck('${id}', this.checked)">
          <label for="${id}" class="cursor-pointer text-sm leading-relaxed">${text}</label>
        </div>`;
      });
      return marked.parse(withChecks);
    },

    async loadCards() {
      try {
        const r = await fetch('/api/exam/' + this.currentExam + '/cards');
        if (!r.ok) return;
        this.cards = (await r.json()).cards || [];
      } catch { /* not available yet */ }
    },

    nextCard() { this.cardFlipped = false; this.cardIndex = Math.min(this.cardIndex + 1, this.filteredCards.length - 1); },
    prevCard()  { this.cardFlipped = false; this.cardIndex = Math.max(this.cardIndex - 1, 0); },

    markCard(rating) {
      if (!this.currentCard) return;
      this.cardProgress[this.currentCard.card_id] = rating;
      localStorage.setItem('cardProgress_' + this.currentExam, JSON.stringify(this.cardProgress));
      this.nextCard();
    },

    shuffleCards()   { this.cards = [...this.cards].sort(() => Math.random() - .5); this.cardIndex = 0; this.cardFlipped = false; },
    resetProgress()  { this.cardProgress = {}; localStorage.removeItem('cardProgress_' + this.currentExam); },
  };
}

window.savePlanCheck = function(id, checked) {
  const exam = document.querySelector('select')?.value || '';
  const key = 'planChecks_' + exam;
  const data = JSON.parse(localStorage.getItem(key) || '{}');
  data[id] = checked;
  localStorage.setItem(key, JSON.stringify(data));
};
</script>
</body>
</html>
"""


if __name__ == "__main__":
    uvicorn.run("web:app", host="0.0.0.0", port=8000, reload=True)
