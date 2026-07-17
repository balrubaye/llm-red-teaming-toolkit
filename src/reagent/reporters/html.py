"""Single-file, offline HTML reporter."""

from __future__ import annotations

import html
import json
from pathlib import Path

from jinja2 import Environment, select_autoescape

from reagent.models import IntervalCI, Scorecard

_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ title }} — {{ scorecard.suite.name }}</title>
<style>
  :root {
    --bg: #0f1115; --fg: #e6e9ef; --muted: #8b94a3;
    --accent: #6ea8ff; --pass: #41c282; --fail: #ff6b6b; --warn: #ffb454;
    --card: #181b22; --border: #252a35;
  }
  @media (prefers-color-scheme: light) {
    :root { --bg:#f7f8fb; --fg:#1a1d24; --muted:#5b6473;
            --accent:#2761d8; --pass:#1a8a55; --fail:#c2334a; --warn:#a8631a;
            --card:#fff; --border:#e1e5ee; }
  }
  * { box-sizing: border-box; }
  body { margin:0; padding:0; font:14px/1.5 system-ui,-apple-system,sans-serif;
         background:var(--bg); color:var(--fg); }
  .wrap { max-width: 1100px; margin: 0 auto; padding: 28px 24px 80px; }
  h1 { font-size: 22px; margin: 0 0 6px; }
  h2 { font-size: 16px; margin: 28px 0 10px; }
  .meta { color: var(--muted); font-size: 13px; }
  .grid { display:grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
          gap: 12px; margin: 16px 0 8px; }
  .tile { background: var(--card); border: 1px solid var(--border);
          border-radius: 8px; padding: 14px; }
  .tile .label { color: var(--muted); font-size: 12px; text-transform: uppercase;
                 letter-spacing: 0.04em; }
  .tile .value { font-size: 22px; font-weight: 600; margin-top: 4px; }
  .tile.pass .value { color: var(--pass); }
  .tile.fail .value { color: var(--fail); }
  table { width:100%; border-collapse: collapse; background: var(--card);
          border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }
  th, td { padding: 9px 12px; text-align: left; border-bottom: 1px solid var(--border);
           vertical-align: top; }
  th { background: rgba(110,168,255,0.06); font-weight: 600; font-size: 12px;
       text-transform: uppercase; letter-spacing: 0.04em; color: var(--muted); }
  tr:last-child td { border-bottom: none; }
  .pill { display:inline-block; padding: 2px 8px; border-radius: 999px;
          font-size: 11px; font-weight: 600; }
  .pill.pass { background: rgba(65,194,130,0.15); color: var(--pass); }
  .pill.fail { background: rgba(255,107,107,0.15); color: var(--fail); }
  .pill.skip { background: rgba(139,148,163,0.18); color: var(--muted); }
  .pill.sev-critical { background: rgba(255,107,107,0.18); color: var(--fail); }
  .pill.sev-high     { background: rgba(255,180,84,0.18); color: var(--warn); }
  .pill.sev-medium   { background: rgba(110,168,255,0.18); color: var(--accent); }
  .pill.sev-low      { background: rgba(139,148,163,0.18); color: var(--muted); }
  details { background: var(--card); border: 1px solid var(--border);
            border-radius: 8px; padding: 8px 12px; margin: 8px 0; }
  details > summary { cursor: pointer; font-weight: 500; }
  pre { background: rgba(0,0,0,0.18); padding: 10px 12px; border-radius: 6px;
        overflow-x: auto; font-size: 12px; }
  .controls { display:flex; gap: 8px; flex-wrap: wrap; margin: 12px 0; }
  .controls input, .controls select {
    background: var(--card); color: var(--fg);
    border: 1px solid var(--border); border-radius: 6px; padding: 6px 10px; font: inherit;
  }
  .footer { color: var(--muted); font-size: 12px; margin-top: 32px; }
  .ci { color: var(--muted); font-size: 12px; }
  .tabs { display: flex; border-bottom: 2px solid var(--border); margin: 28px 0 16px; }
  .tab-btn { background: none; border: none; color: var(--muted); font: inherit; font-weight: 600;
             padding: 10px 16px; cursor: pointer; border-bottom: 2px solid transparent; margin-bottom: -2px; }
  .tab-btn.active { color: var(--accent); border-bottom-color: var(--accent); }
  .tab-content { display: none; }
  .tab-content.active { display: block; }
</style>
</head>
<body>
<div class="wrap">

  <h1>{{ title }}</h1>
  <div class="meta">
    Model <code>{{ scorecard.model.provider }}:{{ scorecard.model.name }}</code> ·
    Suite <code>{{ scorecard.suite.name }}</code> (v{{ scorecard.suite.version }}) ·
    Run <code>{{ scorecard.run_id }}</code> ·
    Reagent {{ scorecard.environment.reagent_version }}
  </div>

  <div class="grid">
    <div class="tile {{ summary_class }}">
      <div class="label">{{ summary_label }}</div>
      <div class="value">{{ summary_value }}</div>
      <div class="ci">95% CI {{ summary_ci }}</div>
    </div>
    <div class="tile">
      <div class="label">Cases</div>
      <div class="value">{{ totals.cases }}</div>
      <div class="ci">{{ totals.passed }} passed · {{ totals.failed }} failed · {{ totals.errored }} errored</div>
    </div>
    <div class="tile">
      <div class="label">Wall clock</div>
      <div class="value">{{ "%.1f"|format(totals.wall_clock_s) }}s</div>
      <div class="ci">Cache {{ totals.cache_hits }}h / {{ totals.cache_misses }}m</div>
    </div>
    <div class="tile">
      <div class="label">Tokens</div>
      <div class="value">{{ totals.tokens_in + totals.tokens_out }}</div>
      <div class="ci">in {{ totals.tokens_in }} · out {{ totals.tokens_out }}</div>
    </div>
  </div>

  {% if scorecard.is_redteam %}
    <div class="tabs">
      <button class="tab-btn active" onclick="switchTab(this, 'owasp')">OWASP LLM Top 10</button>
      <button class="tab-btn" onclick="switchTab(this, 'mitre')">MITRE ATLAS</button>
      <button class="tab-btn" onclick="switchTab(this, 'nist')">NIST AI RMF</button>
    </div>

    <!-- OWASP Content -->
    <div id="tab-owasp" class="tab-content active">
      {% if totals.by_owasp %}
        <table>
          <thead><tr>
            <th>Class</th><th>Cases</th><th>Defended</th><th>Defense rate</th><th>95% CI</th>
          </tr></thead>
          <tbody>
          {% for b in totals.by_owasp %}
            <tr>
              <td>{{ b.owasp.value }}</td>
              <td>{{ b.cases }}</td>
              <td>{{ b.defended }}</td>
              <td>{{ pct(b.defense_rate) }}</td>
              <td class="ci">{{ ci_str(b.defense_rate_ci_95) }}</td>
            </tr>
          {% endfor %}
          </tbody>
        </table>
      {% else %}
        <p class="meta">No cases matching OWASP taxonomy found in this run.</p>
      {% endif %}
    </div>

    <!-- MITRE ATLAS Content -->
    <div id="tab-mitre" class="tab-content">
      {% if totals.by_atlas %}
        <table>
          <thead><tr>
            <th>Technique/Tactic</th><th>ID</th><th>Cases</th><th>Defended</th><th>Defense rate</th><th>95% CI</th>
          </tr></thead>
          <tbody>
          {% for b in totals.by_atlas %}
            <tr>
              <td>{{ b.name }}</td>
              <td><code>{{ b.id }}</code></td>
              <td>{{ b.cases }}</td>
              <td>{{ b.defended }}</td>
              <td>{{ pct(b.defense_rate) }}</td>
              <td class="ci">{{ ci_str(b.defense_rate_ci_95) }}</td>
            </tr>
          {% endfor %}
          </tbody>
        </table>
      {% else %}
        <p class="meta">No cases tagged with MITRE ATLAS identifiers found in this run.</p>
      {% endif %}
    </div>

    <!-- NIST AI RMF Content -->
    <div id="tab-nist" class="tab-content">
      {% if totals.by_nist %}
        <table>
          <thead><tr>
            <th>Function/Category</th><th>ID</th><th>Cases</th><th>Defended</th><th>Defense rate</th><th>95% CI</th>
          </tr></thead>
          <tbody>
          {% for b in totals.by_nist %}
            <tr>
              <td>{{ b.name }}</td>
              <td><code>{{ b.id }}</code></td>
              <td>{{ b.cases }}</td>
              <td>{{ b.defended }}</td>
              <td>{{ pct(b.defense_rate) }}</td>
              <td class="ci">{{ ci_str(b.defense_rate_ci_95) }}</td>
            </tr>
          {% endfor %}
          </tbody>
        </table>
      {% else %}
        <p class="meta">No cases tagged with NIST AI RMF categories found in this run.</p>
      {% endif %}
    </div>
  {% endif %}

  <h2>Cases</h2>
  <div class="controls">
    <input id="filter" type="search" placeholder="Filter by case id, OWASP class, tag…" oninput="filterCases()">
    <select id="status" onchange="filterCases()">
      <option value="all">All</option>
      <option value="fail" selected>Failed only</option>
      <option value="pass">Passed only</option>
    </select>
  </div>

  <div id="cases">
  {% for c in scorecard.cases %}
    <details class="case"
             data-status="{{ 'pass' if c.passed and not c.skipped else ('skip' if c.skipped else 'fail') }}"
             data-search="{{ (c.case_id ~ ' ' ~ (c.owasp.value if c.owasp else '') ~ ' ' ~ (c.tags|join(' ')))|lower }}">
      <summary>
        <span class="pill {{ 'pass' if c.passed and not c.skipped else ('skip' if c.skipped else 'fail') }}">
          {{ 'PASS' if c.passed and not c.skipped else ('SKIP' if c.skipped else 'FAIL') }}
        </span>
        <code>{{ c.case_id }}</code>
        {% if c.owasp %}<span class="pill">{{ c.owasp.value }}</span>{% endif %}
        {% if c.severity %}<span class="pill sev-{{ c.severity.value }}">{{ c.severity.value }}</span>{% endif %}
      </summary>
      {% if c.error %}<p><strong>Error:</strong> {{ c.error }}</p>{% endif %}
      {% if c.request_messages %}
        <h3 style="font-size:13px;margin:10px 0 4px;">Request</h3>
        {% for m in c.request_messages %}
          <pre>[{{ m.role.value }}] {{ m.content }}</pre>
        {% endfor %}
      {% endif %}
      {% if c.response_text %}
        <h3 style="font-size:13px;margin:10px 0 4px;">Response</h3>
        <pre>{{ c.response_text }}</pre>
      {% endif %}
      {% if c.assertion_results %}
        <h3 style="font-size:13px;margin:10px 0 4px;">Assertions</h3>
        <table>
          <thead><tr><th>Kind</th><th>Result</th><th>Detail</th></tr></thead>
          <tbody>
          {% for a in c.assertion_results %}
            <tr>
              <td><code>{{ a.kind }}</code>{% if a.label %} — {{ a.label }}{% endif %}</td>
              <td>
                {% if a.error %}
                  <span class="pill fail">ERR</span>
                {% elif scorecard.is_redteam %}
                  {% if a.passed %}
                    <span class="pill fail">VULN DETECTED</span>
                  {% else %}
                    <span class="pill pass">SAFE</span>
                  {% endif %}
                {% else %}
                  {% if a.passed %}
                    <span class="pill pass">PASS</span>
                  {% else %}
                    <span class="pill fail">FAIL</span>
                  {% endif %}
                {% endif %}
              </td>
              <td>{{ a.error or a.detail or '' }}{% if a.score is not none %} (score={{ "%.2f"|format(a.score) }}){% endif %}</td>
            </tr>
          {% endfor %}
          </tbody>
        </table>
      {% endif %}
      {% if not c.passed and not c.skipped and c.owasp %}
        <div style="margin:16px 0 8px; padding:12px; background:rgba(255,107,107,0.06); border-left:3px solid var(--fail); border-radius:4px;">
          <h3 style="font-size:13px; margin:0 0 6px; color:var(--fail);">Recommended Fix</h3>
          <p style="margin:0; font-size:13px;">{{ c.owasp.remediation }}</p>
        </div>
      {% endif %}
    </details>
  {% endfor %}
  </div>

  <div class="footer">
    Generated by Reagent {{ scorecard.environment.reagent_version }} ·
    Python {{ scorecard.environment.python_version }} ·
    {{ scorecard.environment.platform }}
  </div>
</div>

<script>
  // Embed the raw scorecard so the file is self-describing.
  window.SCORECARD = {{ scorecard_json|safe }};

  function switchTab(btn, tabId) {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
    
    btn.classList.add('active');
    document.getElementById('tab-' + tabId).classList.add('active');
  }

  function filterCases() {
    const q = document.getElementById('filter').value.trim().toLowerCase();
    const status = document.getElementById('status').value;
    for (const el of document.querySelectorAll('.case')) {
      const matchesQuery = !q || el.dataset.search.includes(q);
      const matchesStatus = status === 'all' || el.dataset.status === status;
      el.style.display = (matchesQuery && matchesStatus) ? '' : 'none';
    }
  }
  // Auto-expand failures on load.
  for (const el of document.querySelectorAll('.case[data-status="fail"]')) el.open = true;
  filterCases();
</script>
</body>
</html>
"""


def _fmt_pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def _fmt_ci(ci: IntervalCI | None) -> str:
    if ci is None:
        return "—"
    return f"[{_fmt_pct(ci.low)}, {_fmt_pct(ci.high)}]"


def render_html(scorecard: Scorecard, path: str | Path | None = None) -> str:
    env = Environment(autoescape=select_autoescape(["html", "xml"]))
    env.filters["e"] = html.escape
    tmpl = env.from_string(_TEMPLATE)

    if scorecard.is_redteam and scorecard.totals.defense_rate is not None:
        summary_label = "Defense rate"
        summary_value = _fmt_pct(scorecard.totals.defense_rate)
        summary_ci = _fmt_ci(scorecard.totals.defense_rate_ci_95)
        summary_class = "pass" if scorecard.totals.defense_rate >= 0.95 else "fail"
        title = "🧪 Reagent red-team scorecard"
    else:
        summary_label = "Pass rate"
        summary_value = _fmt_pct(scorecard.totals.pass_rate)
        summary_ci = _fmt_ci(scorecard.totals.pass_rate_ci_95)
        summary_class = "pass" if scorecard.totals.pass_rate >= 0.95 else "fail"
        title = "🧪 Reagent scorecard"

    # Embed the scorecard JSON for downstream tooling. Pydantic v2 handles
    # Decimal / datetime serialization in `mode="json"`.
    scorecard_json = (
        json.dumps(scorecard.model_dump(mode="json"), separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )

    rendered = tmpl.render(
        title=title,
        scorecard=scorecard,
        totals=scorecard.totals,
        summary_label=summary_label,
        summary_value=summary_value,
        summary_ci=summary_ci,
        summary_class=summary_class,
        scorecard_json=scorecard_json,
        pct=_fmt_pct,
        ci_str=_fmt_ci,
    )

    if path is not None:
        p = Path(path).expanduser()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(rendered, encoding="utf-8")
    return rendered


__all__ = ["render_html"]
