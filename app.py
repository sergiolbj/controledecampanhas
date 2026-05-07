import json # Reload trigger 1

from datetime import datetime, timedelta

import extra_streamlit_components as stx  # noqa: F401 (used via _cookie_manager())
import pandas as pd
import plotly.express as px
import streamlit as st

from auth import (
    get_db, init_db, login_ui, logout,
    get_campaigns, create_campaign, update_campaign_client, rename_campaign, delete_campaign,
    get_vehicles, create_vehicle, rename_vehicle, delete_vehicle,
    save_ingestion, load_ingestion, save_user_state, load_user_state,
    get_users, add_user, update_user, delete_user,
    get_clients, add_client, delete_client, rename_client, get_user_clients, set_user_clients,
    create_session, validate_session, delete_session,
    save_campaign_sheets_config, load_campaign_sheets_config,
    has_default_password, get_ingestion_timestamps, get_ingestion_log,
    get_alert_configs, save_alert_config, update_alert_config, delete_alert_config,
    get_mapping_coverage, get_pending_vehicles, clear_campaign_data, restore_ingestion_from_log,
    change_own_password, archive_campaign,
    get_report_recipients, add_report_recipient, toggle_report_recipient, delete_report_recipient,
    log_audit, get_audit_log,
    get_vehicle_notes, add_vehicle_note, delete_vehicle_note,
    get_login_history,
    get_alert_counts,
    get_system_config, set_system_config,
    get_alias_mappings, save_alias, delete_alias,
)

COOKIE_NAME = "adops_session"
COOKIE_DAYS = 7

def _cookie_manager():
    if not st.session_state.get("_cm"):
        st.session_state["_cm"] = stx.CookieManager()
    return st.session_state["_cm"]
from data_processor import (
    ASSET_FIELDS,
    FIELD_LABELS,
    PLAN_FIELDS,
    TAXONOMY_JOIN_FIELDS,
    aggregate_assets,
    apply_mapping,
    compute_veiculacao_status,
    fuzzy_merge_taxonomy,
    fuzzy_taxonomy_report,
    get_sheets,
    get_sheets_from_url,
    merge_taxonomy,
    normalize_dates,
    read_campaign_sheet,
    read_file,
)

from modules.shared import _page_header, _export_buttons
from modules.dialogs import _dlg_del_camp, _dlg_clear_camp, _dlg_del_veh, _dlg_del_cli, _dlg_restore
from modules.mapper import mapper_ui, gantt_chart, save_template, load_templates
from modules.wizard import _copy_ingestion, _duplicate_vehicle_ui, _step_bar, _step_campaign, _step_vehicle
import modules.pages.mapeamento as _pg_map
import modules.pages.dashboard as _pg_dash
import modules.pages.veiculacao as _pg_veic
import modules.pages.gerenciar as _pg_ger
import modules.pages.relatorio as _pg_rel
import modules.pages.clientes as _pg_cli
import modules.pages.usuarios as _pg_usr
import modules.pages.auditoria as _pg_aud

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Controle de Campanhas PPG",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

:root {
  --bg:#f8fafc; --surface:#fff; --sf2:#f1f5f9; --sf3:#e2e8f0;
  --bd:#e2e8f0; --bd2:#cbd5e1;
  --t1:#0f172a; --t2:#475569; --t3:#94a3b8;
  --ac:#2563eb; --ac-bg:#eff6ff; --ac-hov:#1d4ed8;
  --ok:#10b981; --ok-bg:#f0fdf4;
  --warn:#f59e0b; --warn-bg:#fffbeb;
  --err:#ef4444; --err-bg:#fef2f2;
  --topbar:60px; --sidebar:240px;
  --r:10px; --r2:6px;
  --sh:0 1px 3px rgba(0,0,0,.08),0 1px 2px rgba(0,0,0,.04);
  --sh2:0 4px 16px rgba(0,0,0,.08),0 2px 4px rgba(0,0,0,.04);
}

body { font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; }
[data-testid="stTextInput"] input,[data-testid="stTextArea"] textarea,
[data-testid="stNumberInput"] input,[data-testid="stButton"] button,
[data-testid="stMetricLabel"]>div,[data-testid="stMetricValue"]>div,
[data-testid="stCaptionContainer"] p,[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] li,h1,h2,h3 {
  font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif !important; }

html,body { background-color:var(--bg) !important; }
[data-testid="stHeader"]     { display:none !important; }
[data-testid="stDecoration"] { display:none !important; }
footer                        { display:none !important; }

[data-testid="stAppViewContainer"] { background:var(--bg) !important; padding-top:var(--topbar) !important; }
.block-container { padding:2rem 2.5rem 4rem !important; max-width:1400px; }

[data-testid="stSidebar"] {
  background:var(--surface) !important; border-right:1px solid var(--bd) !important;
  top:var(--topbar) !important; height:calc(100vh - var(--topbar)) !important;
  transition:transform .2s ease !important; }
[data-testid="stSidebar"]>div:first-child { padding:0 !important; }
[data-testid="stSidebarContent"] { padding:0 .75rem 1.5rem !important; }
[data-testid="stSidebarCollapseButton"] { display:none !important; }

[data-testid="stSidebar"] [data-testid="stButton"] button {
  border-radius:var(--r2) !important; font-size:.84rem !important;
  font-weight:500 !important; padding:.5rem .75rem !important;
  transition:all .15s !important; width:100% !important; text-align:left !important;
  border:none !important; margin-bottom:2px !important; }
[data-testid="stSidebar"] [data-testid="stButton"] button[kind="secondary"] {
  background:transparent !important; color:var(--t2) !important; }
[data-testid="stSidebar"] [data-testid="stButton"] button[kind="secondary"]:hover {
  background:var(--sf2) !important; color:var(--t1) !important; }
[data-testid="stSidebar"] [data-testid="stButton"] button[kind="primary"] {
  background:var(--ac-bg) !important; color:var(--ac) !important;
  font-weight:600 !important; box-shadow:none !important; }

h1 { font-size:1.5rem !important; font-weight:700 !important; color:var(--t1) !important;
  letter-spacing:-.02em !important; line-height:1.2 !important; margin-bottom:.25rem !important; }
h2 { font-size:1.15rem !important; font-weight:600 !important; color:var(--t1) !important; }
h3 { font-size:1rem !important; font-weight:600 !important; color:var(--t1) !important; }
p, li { color:var(--t2) !important; line-height:1.6 !important; }

[data-testid="stMetric"] {
  background:var(--surface) !important; border:1px solid var(--bd) !important;
  border-radius:var(--r) !important; padding:1.1rem 1.25rem !important;
  transition:border-color .15s,box-shadow .15s !important; }
[data-testid="stMetric"]:hover { border-color:var(--ac) !important;
  box-shadow:0 0 0 3px rgba(37,99,235,.07) !important; }
[data-testid="stMetricLabel"]>div { color:var(--t3) !important; font-size:.7rem !important;
  font-weight:700 !important; text-transform:uppercase !important; letter-spacing:.07em !important; }
[data-testid="stMetricValue"]>div { color:var(--t1) !important; font-size:1.875rem !important;
  font-weight:700 !important; letter-spacing:-.03em !important; }

[data-testid="stButton"] button { border-radius:var(--r2) !important; font-size:.84rem !important;
  font-weight:500 !important; padding:.45rem 1rem !important; transition:all .15s !important;
  border:1px solid transparent !important; }
[data-testid="stButton"] button[kind="primary"] {
  background:var(--ac) !important; color:#fff !important; border-color:var(--ac) !important; }
[data-testid="stButton"] button[kind="primary"]:hover {
  background:var(--ac-hov) !important; box-shadow:0 2px 8px rgba(37,99,235,.35) !important;
  transform:translateY(-1px) !important; }
[data-testid="stButton"] button[kind="secondary"] {
  background:var(--surface) !important; color:var(--t2) !important;
  border-color:var(--bd) !important; }
[data-testid="stButton"] button[kind="secondary"]:hover {
  background:var(--sf2) !important; color:var(--t1) !important; border-color:var(--bd2) !important; }
[data-testid="stDownloadButton"] button {
  background:var(--sf2) !important; border:1px solid var(--bd) !important;
  color:var(--t2) !important; border-radius:var(--r2) !important; }
[data-testid="stDownloadButton"] button:hover {
  background:var(--sf3) !important; color:var(--t1) !important; border-color:var(--bd2) !important; }

[data-testid="stTextInput"] input,[data-testid="stTextArea"] textarea,
[data-testid="stNumberInput"] input {
  background:var(--surface) !important; border:1px solid var(--bd) !important;
  border-radius:var(--r2) !important; color:var(--t1) !important;
  transition:border-color .15s,box-shadow .15s !important; }
[data-testid="stTextInput"] input:focus,[data-testid="stTextArea"] textarea:focus,
[data-testid="stNumberInput"] input:focus {
  border-color:var(--ac) !important; box-shadow:0 0 0 3px rgba(37,99,235,.1) !important; }
[data-testid="stSelectbox"]>div>div,[data-testid="stMultiSelect"]>div>div {
  background:var(--surface) !important; border:1px solid var(--bd) !important;
  border-radius:var(--r2) !important; color:var(--t1) !important; }
[data-testid="stMultiSelect"] span[data-baseweb="tag"] {
  background:var(--ac-bg) !important; border:1px solid var(--ac) !important;
  border-radius:4px !important; color:var(--ac) !important; }

[data-testid="stTabs"] [data-baseweb="tab-list"] {
  background:transparent !important; border-bottom:1px solid var(--bd) !important; }
[data-testid="stTabs"] [data-baseweb="tab"] {
  background:transparent !important; color:var(--t3) !important; font-size:.84rem !important;
  font-weight:500 !important; padding:.5rem 1rem !important;
  border-bottom:2px solid transparent !important; transition:color .15s !important; }
[data-testid="stTabs"] [data-baseweb="tab"]:hover { color:var(--t1) !important; }
[data-testid="stTabs"] [aria-selected="true"] {
  color:var(--ac) !important; border-bottom-color:var(--ac) !important;
  background:var(--ac-bg) !important; }

[data-testid="stExpander"] { border:1px solid var(--bd) !important;
  border-radius:var(--r) !important; background:var(--surface) !important;
  margin-bottom:.5rem !important; overflow:hidden !important; }
[data-testid="stExpander"] details summary { padding:.75rem 1rem !important;
  font-weight:500 !important; font-size:.875rem !important; color:var(--t1) !important; }
[data-testid="stExpander"] details summary:hover { background:var(--sf2) !important; }
[data-testid="stExpander"] details[open] summary { border-bottom:1px solid var(--bd) !important; }

[data-testid="stAlert"] { border-radius:var(--r2) !important; font-size:.875rem !important;
  border-width:1px !important; }
[data-testid="stDataFrame"] { border:1px solid var(--bd) !important;
  border-radius:var(--r) !important; overflow:hidden !important; }
hr { border-color:var(--bd) !important; margin:1rem 0 !important; }
[data-testid="stCaptionContainer"] p { color:var(--t3) !important; font-size:.78rem !important; }
[data-testid="stToggle"] label { color:var(--t2) !important; font-size:.875rem !important; }
::-webkit-scrollbar { width:5px; height:5px; }
::-webkit-scrollbar-track { background:transparent; }
::-webkit-scrollbar-thumb { background:var(--sf3); border-radius:3px; }
[data-testid="stMain"] .block-container { animation:ppgFade .18s ease-in; }
@keyframes ppgFade { from{opacity:0} to{opacity:1} }

/* ── Top bar ── */
#ppg-topbar {
  position:fixed; top:0; left:0; right:0; height:var(--topbar);
  background:var(--surface); border-bottom:1px solid var(--bd);
  display:flex; align-items:center; padding:0 16px; gap:12px;
  z-index:999999; box-shadow:var(--sh);
  font-family:'Inter',-apple-system,sans-serif; }
#ppg-hamburger { width:36px; height:36px; border:none; background:transparent;
  border-radius:var(--r2); cursor:pointer; display:flex; flex-direction:column;
  align-items:center; justify-content:center; gap:4px; transition:background .15s; }
#ppg-hamburger:hover { background:var(--sf2); }
#ppg-hamburger span { width:16px; height:2px; background:var(--t2); border-radius:2px; display:block; }
.ppg-brand { display:flex; align-items:center; gap:10px; text-decoration:none; }
.ppg-brand-icon { width:32px; height:32px; background:linear-gradient(135deg,#2563eb,#1d4ed8);
  border-radius:8px; display:flex; align-items:center; justify-content:center;
  font-size:16px; flex-shrink:0; }
.ppg-brand-name { font-size:.875rem; font-weight:700; color:var(--t1); white-space:nowrap; }
.ppg-brand-sub { font-size:.65rem; color:var(--t3); }
.ppg-sep { width:1px; height:24px; background:var(--bd); flex-shrink:0; }
.ppg-spacer { flex:1; }
.ppg-icon-btn { width:34px; height:34px; border:none; background:transparent;
  border-radius:var(--r2); cursor:pointer; display:flex; align-items:center;
  justify-content:center; color:var(--t2); font-size:14px; position:relative; transition:all .15s; }
.ppg-icon-btn:hover { background:var(--sf2); color:var(--t1); }
.ppg-notif-dot { position:absolute; top:5px; right:5px; width:7px; height:7px;
  background:var(--err); border-radius:50%; border:2px solid var(--surface); }
.ppg-user-chip { display:flex; align-items:center; gap:8px; padding:4px 10px 4px 4px;
  border-radius:20px; cursor:pointer; border:1px solid transparent; transition:all .15s; }
.ppg-user-chip:hover { background:var(--sf2); border-color:var(--bd); }
.ppg-avatar { width:28px; height:28px; background:linear-gradient(135deg,#2563eb,#7c3aed);
  border-radius:50%; display:flex; align-items:center; justify-content:center;
  font-size:11px; font-weight:700; color:#fff; flex-shrink:0; }
.ppg-uname { font-size:.8rem; font-weight:600; color:var(--t1); line-height:1.2; }
.ppg-urole { font-size:.65rem; font-weight:700; text-transform:uppercase; letter-spacing:.06em; }
.ppg-role-admin { color:#f59e0b; }
.ppg-role-editor { color:#10b981; }
.ppg-role-viewer { color:var(--t3); }
</style>
""", unsafe_allow_html=True)


# ── Session state initializer ─────────────────────────────────────────────────
def _init_session_state() -> None:
    """Garante que todas as chaves usadas pelo app existam no session_state."""
    defaults: dict = {
        # Navegação
        "_page": None,
        # Mapeamento & cruzamento
        "plan_df": None, "plan_mapping": {}, "plan_source": None, "plan_config": {},
        "assets_df": None, "assets_mapping": {}, "assets_source": None, "assets_config": {},
        "merged_df": None, "unmatched_df": None, "fuzzy_df": None, "_cross_sig": None,
        "_plan_preview": None, "_assets_preview": None,
        # Campanha / veículo selecionados
        "cfg_campaign_id": None, "cfg_vehicle_id": None,
        # Configs de todas as campanhas (multi-campanha)
        "all_plan_configs": [], "all_assets_configs": [],
        # Cookie manager
        "_cm": None,
        # Batch creation
        "_batch_parsed": None,
        # Misc UI
        "_rpt_html": None,
        "_dark_mode": False,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════════
def main() -> None:
    init_db()
    _init_session_state()

    # ── Loading overlay + barra de progresso ──────────────────────────────────
    import streamlit.components.v1 as _cv1_loader
    _cv1_loader.html("""
<script>
(function () {
  try {
    var doc = window.parent.document;

    /* ── Estilos ── */
    if (!doc.getElementById('ppg-load-css')) {
      var s = doc.createElement('style');
      s.id = 'ppg-load-css';
      s.textContent = [
        /* barra de progresso no topo */
        '#ppg-bar{position:fixed;top:0;left:0;right:0;height:3px;z-index:99999;',
        'background:linear-gradient(90deg,#1a56db 0%,#60a5fa 50%,#1a56db 100%);',
        'background-size:200% 100%;display:none;pointer-events:none}',
        '#ppg-bar.on{display:block;animation:ppgBar 1.2s ease infinite}',
        /* overlay inicial */
        '#ppg-ov{position:fixed;inset:0;background:#0a0e17;z-index:99990;',
        'display:flex;flex-direction:column;align-items:center;justify-content:center;',
        'transition:opacity .35s ease;pointer-events:none}',
        '#ppg-ov.out{opacity:0}',
        /* spinner */
        '#ppg-spin{width:42px;height:42px;border:3px solid #1e2530;',
        'border-top-color:#1a56db;border-radius:50%;animation:ppgSpin .75s linear infinite}',
        '#ppg-lbl{color:#6e7681;font-family:Inter,sans-serif;font-size:13px;',
        'margin-top:14px;letter-spacing:.03em}',
        '@keyframes ppgSpin{to{transform:rotate(360deg)}}',
        '@keyframes ppgBar{0%{background-position:100% 0}100%{background-position:-100% 0}}'
      ].join('');
      doc.head.appendChild(s);
    }

    /* ── Barra de progresso ── */
    var bar = doc.getElementById('ppg-bar');
    if (!bar) {
      bar = doc.createElement('div');
      bar.id = 'ppg-bar';
      doc.body.appendChild(bar);
    }

    /* ── Overlay de carregamento inicial ── */
    var ov = doc.getElementById('ppg-ov');
    if (!ov) {
      ov = doc.createElement('div');
      ov.id = 'ppg-ov';
      ov.innerHTML = '<div id="ppg-spin"></div><div id="ppg-lbl">Carregando...</div>';
      doc.body.appendChild(ov);

      /* Esconde overlay quando o conteúdo principal aparecer */
      var attempts = 0;
      function waitContent() {
        var container = doc.querySelector('[data-testid="stAppViewContainer"]');
        if ((container && container.children.length > 1) || attempts > 60) {
          ov.classList.add('out');
          setTimeout(function(){ ov.style.display = 'none'; }, 380);
        } else {
          attempts++;
          setTimeout(waitContent, 150);
        }
      }
      setTimeout(waitContent, 300);
    }

    /* ── Detecta rerun via StatusWidget ── */
    function checkRunning() {
      var sw = doc.querySelector('[data-testid="stStatusWidget"]');
      var running = sw && sw.offsetParent !== null;
      /* fallback: detecta via atributo aria */
      if (!running) {
        var spinners = doc.querySelectorAll('[aria-label="Running"]');
        running = spinners.length > 0;
      }
      bar.classList.toggle('on', !!running);
    }
    if (!window._ppgLoaderStarted) {
      window._ppgLoaderStarted = true;
      setInterval(checkRunning, 120);
    }

  } catch(e) { /* cross-origin: silencioso */ }
})();
</script>
""", height=0)

    cm = _cookie_manager()

    # ── Restaurar sessão via cookie ───────────────────────────────────────────
    # CookieManager (extra_streamlit_components) needs one JS round-trip before
    # cookies are readable. On that first pass cm.get() returns None for everything.
    # We detect this with a one-shot sentinel: if "_cm_ready" isn't set yet, we
    # trigger a silent rerun instead of showing the login form as a ghost frame.
    if not st.session_state.get("logged_in"):
        if not st.session_state.get("_cm_ready"):
            st.session_state["_cm_ready"] = True
            st.rerun()
        token = cm.get(COOKIE_NAME)
        if token:
            result = validate_session(token)
            if result:
                uname, urole = result
                st.session_state.update(
                    logged_in=True, username=uname, role=urole, _session_token=token
                )

    if not st.session_state.get("logged_in"):
        login_ui()
        return

    # ── Gravar cookie após login ──────────────────────────────────────────────
    if st.session_state.pop("_just_logged_in", False):
        token = create_session(
            st.session_state["username"], st.session_state["role"], COOKIE_DAYS
        )
        st.session_state["_session_token"] = token
        cm.set(COOKIE_NAME, token,
               expires_at=datetime.now() + timedelta(days=COOKIE_DAYS))

    role     = st.session_state["role"]
    username = st.session_state["username"]

    # ── Tema dark: injeta override CSS quando ativo ───────────────────────────
    _dark = st.session_state.get("_dark_mode", False)
    if _dark:
        st.markdown("""
<style>
:root {
  --bg:#0f172a; --surface:#1e293b; --sf2:#0f172a; --sf3:#334155;
  --bd:#334155; --bd2:#475569;
  --t1:#f1f5f9; --t2:#94a3b8; --t3:#64748b;
  --ac:#3b82f6; --ac-bg:rgba(59,130,246,.15); --ac-hov:#60a5fa;
  --ok:#34d399; --ok-bg:rgba(52,211,153,.1);
  --warn:#fbbf24; --warn-bg:rgba(251,191,36,.1);
  --err:#f87171; --err-bg:rgba(248,113,113,.1);
  --sh:0 1px 3px rgba(0,0,0,.4),0 1px 2px rgba(0,0,0,.3);
  --sh2:0 4px 16px rgba(0,0,0,.4),0 2px 4px rgba(0,0,0,.3);
}
html, body,
[data-testid="stApp"],
[data-testid="stAppViewContainer"],
[data-testid="stMain"],
section.main { background-color:#0f172a !important; }
[data-testid="stSidebar"] { background:#1e293b !important; border-right-color:#334155 !important; }
.stSelectbox > div, .stMultiSelect > div { background:#1e293b !important; }
[data-baseweb="select"] > div { background:#1e293b !important; border-color:#334155 !important; color:#f1f5f9 !important; }
[data-baseweb="popover"] ul { background:#1e293b !important; }
[data-baseweb="popover"] li { color:#f1f5f9 !important; }
[data-baseweb="popover"] li:hover { background:#334155 !important; }
[data-testid="stForm"] { background:#1e293b !important; border-color:#334155 !important; }
[data-baseweb="tab-panel"] { background:transparent !important; }
[data-testid="stDataFrame"] { border-color:#334155 !important; }
</style>
""", unsafe_allow_html=True)

    # ── Top bar injetado via HTML ─────────────────────────────────────────────
    _initials = (username[:2].upper() if username else "??")
    _role_class = {"admin": "ppg-role-admin", "editor": "ppg-role-editor"}.get(role, "ppg-role-viewer")
    _ac = get_alert_counts(username, role)
    _notif_dot = '<span class="ppg-notif-dot"></span>' if _ac["total"] > 0 else ""
    st.markdown(f"""
    <div id="ppg-topbar">
      <button id="ppg-hamburger" onclick="ppgToggleSidebar()" aria-label="Menu">
        <span></span><span></span><span></span>
      </button>
      <a class="ppg-brand" href="#">
        <div class="ppg-brand-icon">📊</div>
        <div>
          <div class="ppg-brand-name">Campanhas PPG</div>
          <div class="ppg-brand-sub">Campaign Management</div>
        </div>
      </a>
      <div class="ppg-sep"></div>
      <div class="ppg-spacer"></div>
      <div class="ppg-user-chip">
        <div class="ppg-avatar">{_initials}</div>
        <div>
          <div class="ppg-uname">{username}</div>
          <div class="ppg-urole {_role_class}">{role.upper()}</div>
        </div>
      </div>
    </div>
    <script>
    function ppgToggleSidebar() {{
      try {{
        var doc  = window.parent.document;
        var sb   = doc.querySelector('[data-testid="stSidebar"]');
        var main = doc.querySelector('[data-testid="stMain"]');
        if (!sb) return;
        var hidden = sb.style.transform === 'translateX(-100%)';
        sb.style.transform  = hidden ? '' : 'translateX(-100%)';
        sb.style.opacity    = hidden ? '1' : '0';
        if (main) main.style.marginLeft = hidden ? '' : '0';
      }} catch(e) {{}}
    }}
    </script>
    """, unsafe_allow_html=True)

    # ── (Memória automática removida a pedido do usuário) ─────────────────────
    # ── Cruzamento automático global (roda em qualquer página) ────────────────
    if ("plan_df" in st.session_state and "assets_df" in st.session_state
            and "merged_df" not in st.session_state):
        _pdf = st.session_state["plan_df"]
        _adf = st.session_state["assets_df"]
        _avail = [f for f in TAXONOMY_JOIN_FIELDS
                  if f in _pdf.columns and f in _adf.columns]
        if _avail:
            from data_processor import apply_aliases
            _aliases = get_alias_mappings()
            _pdf = apply_aliases(_pdf, _aliases, _avail)
            _agg = aggregate_assets(_adf, _avail)
            _matched, _unmatched = fuzzy_merge_taxonomy(_pdf, _agg, _avail, 80)
            _matched = compute_veiculacao_status(_matched)
            st.session_state.update(
                merged_df=_matched,
                unmatched_df=_unmatched,
                fuzzy_df=fuzzy_taxonomy_report(_pdf, _agg, _avail, 80),
            )

    # ── Sidebar nav ───────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown('<div style="height:8px"></div>', unsafe_allow_html=True)

        # Aviso de senha padrão (item 3)
        if has_default_password(username):
            st.warning("⚠️ Você está usando a senha padrão. Altere-a abaixo.", icon="🔒")

        # ── Toggle tema ───────────────────────────────────────────────────────
        _dark_now = st.session_state.get("_dark_mode", False)
        _theme_label = "🌙 Tema Escuro" if not _dark_now else "☀️ Tema Claro"
        if st.button(_theme_label, use_container_width=True, key="toggle_theme"):
            st.session_state["_dark_mode"] = not _dark_now
            st.rerun()

        # ── Item 25: troca de senha ───────────────────────────────────────
        with st.expander("🔑 Minha Conta", expanded=False):
            st.caption(f"Usuário: **{username}** · Perfil: `{role.upper()}`")
            _pw_cur  = st.text_input("Senha atual",       type="password", key="pw_cur")
            _pw_new  = st.text_input("Nova senha",        type="password", key="pw_new")
            _pw_conf = st.text_input("Confirmar nova senha", type="password", key="pw_conf")
            if st.button("Alterar senha", key="pw_change"):
                if not _pw_cur or not _pw_new:
                    st.warning("Preencha todos os campos.")
                elif _pw_new != _pw_conf:
                    st.error("As novas senhas não coincidem.")
                elif len(_pw_new) < 6:
                    st.warning("A nova senha deve ter pelo menos 6 caracteres.")
                else:
                    if change_own_password(username, _pw_cur, _pw_new):
                        st.toast("Senha alterada com sucesso!", icon="🔐")
                    else:
                        st.error("Senha atual incorreta.")

        st.divider()
        if "page" not in st.session_state:
            st.session_state["page"] = "📊 Dashboard"

        page = st.session_state["page"]

        # ── Bloco principal: visualização (item 4: type="primary" na página ativa) ──
        def _nav(label: str, target: str, clear_keys: list[str] | None = None):
            is_active = page == target
            if st.button(label, use_container_width=True,
                         type="primary" if is_active else "secondary"):
                if clear_keys:
                    for k in clear_keys:
                        st.session_state.pop(k, None)
                st.session_state["page"] = target
                st.rerun()

        # ── Item 32: badges de alerta ─────────────────────────────────────
        _ac = get_alert_counts(username, role)
        _badge = f" 🔴 {_ac['total']}" if _ac["total"] > 0 else ""

        _nav("📊 Dashboard" + _badge, "📊 Dashboard",
             ["plan_df", "assets_df", "merged_df", "unmatched_df", "fuzzy_df",
              "all_plan_configs", "all_assets_configs", "_cross_sig",
              "cfg_campaign_id", "cfg_campaign_name"])
        _nav("📡 Campanhas em Veiculação", "📡 Campanhas em Veiculação")
        _nav("📄 Relatório", "📄 Relatório")

        # ── Bloco de configuração (admin/editor) ──────────────────────────
        if role in ["admin", "editor"]:
            st.divider()
            st.caption("⚙️ CONFIGURAÇÃO")
            _nav("📥 Mapeamento & Cruzamento", "📥 Mapeamento & Cruzamento",
                 ["cfg_campaign_id", "cfg_campaign_name", "cfg_vehicle_id", "cfg_vehicle_name",
                  "plan_df", "assets_df", "merged_df", "unmatched_df", "fuzzy_df"])
            _nav("⚙️ Gerenciar Campanhas", "⚙️ Gerenciar Campanhas")
            _nav("🏢 Clientes", "🏢 Clientes")
            _nav("👥 Usuários", "👥 Usuários")
            if role == "admin":
                _nav("📋 Auditoria", "📋 Auditoria")

        # ── Item 16: busca global de campanha ────────────────────────────────
        st.divider()
        _sq = st.text_input("🔍 Buscar campanha", placeholder="Nome ou cliente…", key="sb_search",
                            label_visibility="collapsed")
        if _sq.strip():
            _all = get_campaigns(username=username, role=role)
            _ql  = _sq.strip().lower()
            _hits = [c for c in _all if _ql in c["name"].lower()
                     or _ql in (c.get("client_name") or "").lower()]
            if _hits:
                for _h in _hits[:6]:
                    _lbl = _h["name"] + (f" · {_h['client_name']}" if _h.get("client_name") else "")
                    if st.button(_lbl, key=f"sb_hit_{_h['id']}", use_container_width=True):
                        for _k in ["plan_df", "assets_df", "merged_df", "unmatched_df",
                                   "fuzzy_df", "_cross_sig", "all_plan_configs", "all_assets_configs"]:
                            st.session_state.pop(_k, None)
                        st.session_state.update(
                            page="📊 Dashboard",
                            cfg_campaign_id=_h["id"],
                            cfg_campaign_name=_h["name"],
                        )
                        st.rerun()
            else:
                st.caption("Nenhuma campanha encontrada.")
        st.divider()
        if st.button("⏏ Sair", use_container_width=True):
            token = st.session_state.get("_session_token")
            if token:
                delete_session(token)
            cm.delete(COOKIE_NAME)
            logout()

    # ── Page routing ──────────────────────────────────────────────────────────
    if page == "📥 Mapeamento & Cruzamento":
        _pg_map.render(username, role)
    elif page == "📊 Dashboard":
        _pg_dash.render(username, role)
    elif page == "📡 Campanhas em Veiculação":
        _pg_veic.render(username, role)
    elif page == "⚙️ Gerenciar Campanhas":
        _pg_ger.render(username, role)
    elif page == "📄 Relatório":
        _pg_rel.render(username, role)
    elif page == "🏢 Clientes":
        _pg_cli.render(username, role)
    elif page == "👥 Usuários":
        _pg_usr.render(username, role)
    elif page == "📋 Auditoria":
        _pg_aud.render(username, role)


if __name__ == "__main__":
    main()
