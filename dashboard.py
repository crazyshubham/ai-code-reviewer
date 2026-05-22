import os
os.environ["GEMINI_API_KEY"] = "AIzaSyD-HxY7m6h3j2VvrdjToJtB9fbY5ETw77g"
import streamlit as st
import pandas as pd
import time

# ─────────────────────────────────────────────
# Page config — must be first Streamlit calls
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="AI Code Review Agent",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────
# Custom CSS — dark terminal-inspired theme
# ─────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=Syne:wght@400;700;800&display=swap');

/* ── Root vars ── */
:root {
    --bg:        #0d0f14;
    --surface:   #141720;
    --surface2:  #1c2030;
    --border:    #252a3a;
    --accent:    #4fffb0;
    --accent2:   #7b9cff;
    --red:       #ff4f6a;
    --yellow:    #ffca4f;
    --green:     #4fffb0;
    --text:      #e2e8f0;
    --muted:     #6b7a99;
    --mono:      'JetBrains Mono', monospace;
    --display:   'Syne', sans-serif;
}

/* ── Global ── */
html, body, [class*="css"] {
    background-color: var(--bg) !important;
    color: var(--text) !important;
    font-family: var(--mono) !important;
}

/* ── Hide Streamlit chrome ── */
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding: 2rem 2.5rem 4rem !important; max-width: 1400px; }

/* ── Header ── */
.hero-header {
    display: flex;
    align-items: baseline;
    gap: 1rem;
    margin-bottom: 0.25rem;
}
.hero-title {
    font-family: var(--display);
    font-size: 2.4rem;
    font-weight: 800;
    color: var(--accent);
    letter-spacing: -0.02em;
    margin: 0;
}
.hero-sub {
    font-size: 0.75rem;
    color: var(--muted);
    letter-spacing: 0.15em;
    text-transform: uppercase;
}
.hero-divider {
    height: 1px;
    background: linear-gradient(90deg, var(--accent) 0%, transparent 60%);
    margin: 1rem 0 2rem 0;
}

/* ── Input row ── */
.stTextInput > div > div > input {
    background: var(--surface2) !important;
    border: 1px solid var(--border) !important;
    border-radius: 6px !important;
    color: var(--text) !important;
    font-family: var(--mono) !important;
    font-size: 0.85rem !important;
    padding: 0.6rem 1rem !important;
}
.stTextInput > div > div > input:focus {
    border-color: var(--accent) !important;
    box-shadow: 0 0 0 2px rgba(79,255,176,0.15) !important;
}
.stTextInput > label {
    color: var(--muted) !important;
    font-size: 0.75rem !important;
    letter-spacing: 0.1em !important;
    text-transform: uppercase !important;
}

/* ── Button ── */
.stButton > button {
    background: var(--accent) !important;
    color: #0d0f14 !important;
    font-family: var(--display) !important;
    font-weight: 700 !important;
    font-size: 0.85rem !important;
    letter-spacing: 0.08em !important;
    border: none !important;
    border-radius: 6px !important;
    padding: 0.55rem 1.8rem !important;
    transition: opacity 0.2s !important;
}
.stButton > button:hover { opacity: 0.85 !important; }

/* ── Metric cards ── */
.metric-row { display: flex; gap: 1rem; margin-bottom: 2rem; flex-wrap: wrap; }
.metric-card {
    flex: 1;
    min-width: 140px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 1.2rem 1.4rem;
    position: relative;
    overflow: hidden;
}
.metric-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
}
.metric-card.accent::before  { background: var(--accent); }
.metric-card.danger::before  { background: var(--red); }
.metric-card.warn::before    { background: var(--yellow); }
.metric-card.info::before    { background: var(--accent2); }
.metric-label {
    font-size: 0.68rem;
    color: var(--muted);
    letter-spacing: 0.12em;
    text-transform: uppercase;
    margin-bottom: 0.4rem;
}
.metric-value {
    font-family: var(--display);
    font-size: 2rem;
    font-weight: 800;
    line-height: 1;
}
.metric-card.accent .metric-value  { color: var(--accent); }
.metric-card.danger .metric-value  { color: var(--red); }
.metric-card.warn .metric-value    { color: var(--yellow); }
.metric-card.info .metric-value    { color: var(--accent2); }

/* ── Section labels ── */
.section-label {
    font-size: 0.7rem;
    letter-spacing: 0.2em;
    text-transform: uppercase;
    color: var(--muted);
    margin-bottom: 1rem;
    padding-bottom: 0.4rem;
    border-bottom: 1px solid var(--border);
}

/* ── Review cards ── */
.review-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 1.2rem 1.4rem;
    margin-bottom: 1rem;
    border-left: 3px solid transparent;
    transition: border-color 0.2s;
}
.review-card.sev-high   { border-left-color: var(--red); }
.review-card.sev-medium { border-left-color: var(--yellow); }
.review-card.sev-low    { border-left-color: var(--green); }

.card-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 0.8rem;
    flex-wrap: wrap;
    gap: 0.5rem;
}
.card-location {
    font-size: 0.75rem;
    color: var(--muted);
    font-family: var(--mono);
}
.card-location span { color: var(--accent2); }

.badge {
    display: inline-block;
    font-size: 0.65rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    padding: 0.2rem 0.55rem;
    border-radius: 4px;
    margin-right: 0.4rem;
}
.badge-high     { background: rgba(255,79,106,0.15); color: var(--red);    border: 1px solid rgba(255,79,106,0.3); }
.badge-medium   { background: rgba(255,202,79,0.12); color: var(--yellow); border: 1px solid rgba(255,202,79,0.3); }
.badge-low      { background: rgba(79,255,176,0.1);  color: var(--green);  border: 1px solid rgba(79,255,176,0.25); }
.badge-security { background: rgba(255,79,106,0.1);  color: var(--red);    border: 1px solid rgba(255,79,106,0.2); }
.badge-bug      { background: rgba(255,202,79,0.1);  color: var(--yellow); border: 1px solid rgba(255,202,79,0.2); }
.badge-style    { background: rgba(123,156,255,0.1); color: var(--accent2);border: 1px solid rgba(123,156,255,0.2); }
.badge-perf     { background: rgba(79,255,176,0.1);  color: var(--green);  border: 1px solid rgba(79,255,176,0.2); }
.badge-verify   { background: rgba(255,202,79,0.18); color: var(--yellow); border: 1px solid var(--yellow); font-size: 0.7rem; }

.card-comment { font-size: 0.88rem; color: var(--text); margin-bottom: 0.6rem; line-height: 1.5; }
.card-suggestion {
    font-size: 0.8rem;
    color: var(--accent);
    background: rgba(79,255,176,0.05);
    border: 1px solid rgba(79,255,176,0.15);
    border-radius: 5px;
    padding: 0.5rem 0.8rem;
    margin-bottom: 0.8rem;
}
.card-suggestion::before { content: "💡 "; }

/* ── Confidence bar ── */
.conf-row { display: flex; align-items: center; gap: 0.8rem; }
.conf-label { font-size: 0.68rem; color: var(--muted); letter-spacing: 0.08em; min-width: 90px; }
.conf-track {
    flex: 1;
    height: 5px;
    background: var(--border);
    border-radius: 99px;
    overflow: hidden;
}
.conf-fill {
    height: 100%;
    border-radius: 99px;
    transition: width 0.6s ease;
}
.conf-val { font-size: 0.75rem; font-weight: 600; min-width: 36px; text-align: right; }

/* ── Sidebar ── */
section[data-testid="stSidebar"] {
    background: var(--surface) !important;
    border-right: 1px solid var(--border) !important;
}
section[data-testid="stSidebar"] .stMultiSelect > label,
section[data-testid="stSidebar"] .stSelectbox > label,
section[data-testid="stSidebar"] label {
    color: var(--muted) !important;
    font-size: 0.72rem !important;
    letter-spacing: 0.1em !important;
    text-transform: uppercase !important;
}

/* ── Download button ── */
.stDownloadButton > button {
    background: var(--surface2) !important;
    color: var(--accent) !important;
    border: 1px solid var(--accent) !important;
    font-family: var(--mono) !important;
    font-size: 0.8rem !important;
    border-radius: 6px !important;
}

/* ── Spinner ── */
.stSpinner > div { border-top-color: var(--accent) !important; }

/* ── Empty state ── */
.empty-state {
    text-align: center;
    padding: 4rem 2rem;
    color: var(--muted);
}
.empty-state .icon { font-size: 3rem; margin-bottom: 1rem; }
.empty-state p { font-size: 0.85rem; line-height: 1.6; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# Mock data  (replace with real pipeline later)
# ─────────────────────────────────────────────
MOCK_REVIEWS = {
    "reviews": [
        {
            "file": "app.py", "function": "login",
            "category": "security", "severity": "high",
            "comment": "Password stored in plaintext — this exposes user credentials if the database is compromised.",
            "suggestion": "Use bcrypt hashing via `bcrypt.hashpw(password, bcrypt.gensalt())`.",
            "confidence": 95, "verify": False, "line": 23,
        },
        {
            "file": "utils.py", "function": "query_db",
            "category": "bug", "severity": "medium",
            "comment": "Missing null check on query result before accessing `.rows`.",
            "suggestion": "Add `if result is None: return []` before accessing result attributes.",
            "confidence": 42, "verify": True, "line": 67,
        },
        {
            "file": "api/routes.py", "function": "get_user",
            "category": "security", "severity": "high",
            "comment": "No rate limiting on this endpoint — susceptible to brute-force enumeration.",
            "suggestion": "Apply `flask_limiter` or similar middleware: `@limiter.limit('10/minute')`.",
            "confidence": 88, "verify": False, "line": 112,
        },
        {
            "file": "helpers.py", "function": "parse_csv",
            "category": "bug", "severity": "low",
            "comment": "File handle opened but not closed if an exception is raised mid-parse.",
            "suggestion": "Wrap file I/O in a `with open(path) as f:` context manager.",
            "confidence": 78, "verify": False, "line": 45,
        },
        {
            "file": "models/user.py", "function": "save",
            "category": "style", "severity": "low",
            "comment": "Function is 90 lines long and handles validation, DB write, and email dispatch — violates single-responsibility principle.",
            "suggestion": "Extract into `validate_user()`, `persist_user()`, and `send_welcome_email()` methods.",
            "confidence": 35, "verify": True, "line": 200,
        },
    ],
    "total_issues": 5,
    "high_severity": 2,
    "low_confidence_count": 2,
    "files_analyzed": 4,
}


# ─────────────────────────────────────────────
# Helper: render a review card
# ─────────────────────────────────────────────
def severity_class(sev: str) -> str:
    return {"high": "sev-high", "medium": "sev-medium", "low": "sev-low"}.get(sev, "sev-low")

def conf_color(score: int) -> str:
    if score >= 75: return "#4fffb0"
    if score >= 50: return "#ffca4f"
    return "#ff4f6a"

def category_badge(cat: str) -> str:
    mapping = {"security": "badge-security", "bug": "badge-bug",
                "style": "badge-style", "performance": "badge-perf"}
    cls = mapping.get(cat, "badge-style")
    return f'<span class="badge {cls}">{cat}</span>'

def render_card(r: dict):
    sev_cls  = severity_class(r["severity"])
    color    = conf_color(r["confidence"])
    verify   = '&nbsp;<span class="badge badge-verify">⚠️ VERIFY THIS</span>' if r["verify"] else ""
    cat_html = category_badge(r["category"])

    st.markdown(f"""
    <div class="review-card {sev_cls}">
      <div class="card-header">
        <div>
          <div class="card-location">
            <span>{r['file']}</span> · {r['function']}() · line {r['line']}
          </div>
        </div>
        <div>
          {cat_html}
          <span class="badge badge-{r['severity']}">{r['severity']}</span>
          {verify}
        </div>
      </div>
      <div class="card-comment">{r['comment']}</div>
      <div class="card-suggestion">{r['suggestion']}</div>
      <div class="conf-row">
        <span class="conf-label">CONFIDENCE</span>
        <div class="conf-track">
          <div class="conf-fill" style="width:{r['confidence']}%; background:{color};"></div>
        </div>
        <span class="conf-val" style="color:{color};">{r['confidence']}%</span>
      </div>
    </div>
    """, unsafe_allow_html=True)


# ─────────────────────────────────────────────
# App state
# ─────────────────────────────────────────────
if "results" not in st.session_state:
    st.session_state.results = None
if "repo_analyzed" not in st.session_state:
    st.session_state.repo_analyzed = ""


# ─────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────
st.markdown("""
<div class="hero-header">
  <p class="hero-title">AI Code Review Agent</p>
</div>
<p class="hero-sub">Autonomous · AST-Powered · Confidence-Rated</p>
<div class="hero-divider"></div>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# Input row
# ─────────────────────────────────────────────
col_input, col_btn = st.columns([5, 1])
with col_input:
    github_url = st.text_input(
        "GitHub Repository URL",
        placeholder="https://github.com/owner/repo",
        label_visibility="visible",
    )
with col_btn:
    st.markdown("<div style='height:1.9rem'></div>", unsafe_allow_html=True)
    analyze_clicked = st.button("Analyze →", use_container_width=True)


# ─────────────────────────────────────────────
# Analysis trigger
# ─────────────────────────────────────────────
if analyze_clicked:
    if not github_url.strip():
        st.warning("Please enter a GitHub repository URL.")
    else:
        with st.spinner("Cloning repository…"):
            from ingestion import clone_and_read
            ingestion_output = clone_and_read(github_url)

        if ingestion_output["error"]:
            st.error(f"Ingestion failed: {ingestion_output['error']}")
        else:
            with st.spinner(f"Parsing {ingestion_output['total_files']} files…"):
                from parser import parse_files
                parsed = parse_files(ingestion_output)

            with st.spinner("Reviewing with Gemini"):
                from reviewer import review_code
                results = review_code(parsed)
                results["files_analyzed"] = ingestion_output["total_files"]

            st.session_state.results = results
            st.session_state.repo_analyzed = github_url

# ─────────────────────────────────────────────
# Results
# ─────────────────────────────────────────────
if st.session_state.results:
    data = st.session_state.results
    reviews_all = data["reviews"]

    # ── Sidebar filters ──────────────────────
    with st.sidebar:
    api_key = st.text_input("Gemini API Key", type="password")
    if api_key:
        os.environ["GEMINI_API_KEY"] = api_key
    st.markdown("### 🎛 Filters")

        all_cats = sorted(set(r["category"] for r in reviews_all))
        sel_cats = st.multiselect("Category", all_cats, default=all_cats)

        all_sevs = ["high", "medium", "low"]
        sel_sevs = st.multiselect("Severity", all_sevs, default=all_sevs)

        st.markdown("---")
        only_verify = st.checkbox("Show only ⚠️ Verify items", value=False)

        st.markdown("---")
        st.markdown(f"<div style='font-size:0.72rem; color:#6b7a99;'>Repo<br><span style='color:#7b9cff; word-break:break-all;'>{st.session_state.repo_analyzed}</span></div>", unsafe_allow_html=True)

    # ── Apply filters ────────────────────────
    reviews = [
        r for r in reviews_all
        if r["category"] in sel_cats
        and r["severity"] in sel_sevs
        and (not only_verify or r["verify"])
    ]

    # ── Metric cards ─────────────────────────
    files_count = len(set(r["file"] for r in reviews_all))
    low_conf    = sum(1 for r in reviews_all if r["verify"])

    st.markdown(f"""
    <div class="metric-row">
      <div class="metric-card accent">
        <div class="metric-label">Total Issues</div>
        <div class="metric-value">{len(reviews_all)}</div>
      </div>
      <div class="metric-card danger">
        <div class="metric-label">High Severity</div>
        <div class="metric-value">{sum(1 for r in reviews_all if r['severity']=='high')}</div>
      </div>
      <div class="metric-card warn">
        <div class="metric-label">Low Confidence</div>
        <div class="metric-value">{low_conf}</div>
      </div>
      <div class="metric-card info">
        <div class="metric-label">Files Analyzed</div>
        <div class="metric-value">{files_count}</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Main review list ─────────────────────
    main_reviews = [r for r in reviews if not r["verify"]]
    low_conf_reviews = [r for r in reviews if r["verify"]]

    st.markdown('<div class="section-label">Review Comments</div>', unsafe_allow_html=True)

    if main_reviews:
        for r in sorted(main_reviews, key=lambda x: {"high":0,"medium":1,"low":2}[x["severity"]]):
            render_card(r)
    else:
        st.markdown('<div style="color:#6b7a99; font-size:0.85rem; padding: 1rem 0;">No issues match current filters.</div>', unsafe_allow_html=True)

    # ── Low-confidence section ────────────────
    if low_conf_reviews:
        st.markdown('<div class="section-label" style="margin-top:2rem;">⚠️ Low Confidence Reviews — Verify These</div>', unsafe_allow_html=True)
        st.markdown('<div style="font-size:0.78rem; color:#6b7a99; margin-bottom:1rem;">These comments scored below 50% confidence. Treat as hints, not conclusions.</div>', unsafe_allow_html=True)
        for r in low_conf_reviews:
            render_card(r)

    # ── Download CSV ─────────────────────────
    st.markdown("<div style='margin-top: 2rem;'></div>", unsafe_allow_html=True)
    df = pd.DataFrame(reviews_all)
    csv_bytes = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="⬇ Export Results as CSV",
        data=csv_bytes,
        file_name="code_review_results.csv",
        mime="text/csv",
    )

else:
    # ── Empty / welcome state ─────────────────
    st.markdown("""
    <div class="empty-state">
      <div class="icon">🔍</div>
      <p>
        Enter a public GitHub repository URL above and click <strong>Analyze →</strong><br>
        The agent will clone the repo, parse source files with AST,<br>
        and return confidence-rated review comments.
      </p>
    </div>
    """, unsafe_allow_html=True)
