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
/* ── Google Fonts ─────────────────────────────────────────────────────────── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

/* ── Reset / Base ─────────────────────────────────────────────────────────── */
/* Definir Inter no body SEM !important para que elementos com font-family
   explícita (Material Icons, Material Symbols) consigam sobrescrever normalmente */
body {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}
/* Forçar Inter apenas nos elementos onde temos certeza que é texto (não ícone) */
[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea,
[data-testid="stNumberInput"] input,
[data-testid="stButton"] button,
[data-testid="stMetricLabel"] > div,
[data-testid="stMetricValue"] > div,
[data-testid="stCaptionContainer"] p,
[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] li,
[data-testid="stMarkdownContainer"] h1,
[data-testid="stMarkdownContainer"] h2,
[data-testid="stMarkdownContainer"] h3,
h1, h2, h3 {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
}

/* Base escura imediata (evita flash branco antes do JS carregar) */
html, body { background-color: #0a0e17 !important; }

/* Esconde chrome do Streamlit */
[data-testid="stHeader"]     { display: none !important; }
[data-testid="stDecoration"] { display: none !important; }
footer                        { display: none !important; }

/* ── Layout ───────────────────────────────────────────────────────────────── */
[data-testid="stAppViewContainer"] { background: #0a0e17; }
.block-container { padding: 2rem 2.5rem 4rem !important; max-width: 1400px; }

/* ── Sidebar ──────────────────────────────────────────────────────────────── */
[data-testid="stSidebar"] {
  background: #0d1117 !important;
  border-right: 1px solid #1e2530 !important;
}
[data-testid="stSidebar"] > div:first-child { padding: 0 !important; }
[data-testid="stSidebarContent"] { padding: 0 1rem 1.5rem !important; }

/* Nav buttons na sidebar */
[data-testid="stSidebar"] [data-testid="stButton"] button {
  border-radius: 8px !important;
  font-size: 0.85rem !important;
  font-weight: 500 !important;
  padding: 0.5rem 0.75rem !important;
  transition: all 0.15s ease !important;
  width: 100% !important;
  text-align: left !important;
  border: none !important;
  margin-bottom: 2px !important;
}
[data-testid="stSidebar"] [data-testid="stButton"] button[kind="secondary"] {
  background: transparent !important;
  color: #8b949e !important;
}
[data-testid="stSidebar"] [data-testid="stButton"] button[kind="secondary"]:hover {
  background: #161b22 !important;
  color: #e6edf3 !important;
}
[data-testid="stSidebar"] [data-testid="stButton"] button[kind="primary"] {
  background: linear-gradient(135deg, #1a56db 0%, #1e40af 100%) !important;
  color: #ffffff !important;
  box-shadow: 0 1px 4px rgba(26,86,219,.4) !important;
}

/* ── Tipografia ───────────────────────────────────────────────────────────── */
h1 {
  font-size: 1.7rem !important;
  font-weight: 700 !important;
  color: #e6edf3 !important;
  letter-spacing: -0.03em !important;
  line-height: 1.2 !important;
  margin-bottom: 0.25rem !important;
}
h2 { font-size: 1.2rem !important; font-weight: 600 !important; color: #cdd9e5 !important; }
h3 { font-size: 1rem !important;   font-weight: 600 !important; color: #cdd9e5 !important; }
p, li { color: #cdd9e5 !important; line-height: 1.6 !important; }

/* ── Metrics ──────────────────────────────────────────────────────────────── */
[data-testid="stMetric"] {
  background: #111827 !important;
  border: 1px solid #1e2530 !important;
  border-radius: 12px !important;
  padding: 1.1rem 1.25rem !important;
  transition: border-color 0.15s !important;
}
[data-testid="stMetric"]:hover { border-color: #30363d !important; }
[data-testid="stMetricLabel"] > div {
  color: #6e7681 !important;
  font-size: 0.72rem !important;
  font-weight: 600 !important;
  text-transform: uppercase !important;
  letter-spacing: 0.07em !important;
}
[data-testid="stMetricValue"] > div {
  color: #e6edf3 !important;
  font-size: 2rem !important;
  font-weight: 700 !important;
  letter-spacing: -0.03em !important;
}

/* ── Botões ───────────────────────────────────────────────────────────────── */
[data-testid="stButton"] button {
  border-radius: 8px !important;
  font-size: 0.85rem !important;
  font-weight: 500 !important;
  padding: 0.45rem 1rem !important;
  transition: all 0.15s ease !important;
  border: 1px solid transparent !important;
  letter-spacing: 0.01em !important;
}
[data-testid="stButton"] button[kind="primary"] {
  background: linear-gradient(135deg, #1a56db 0%, #1e40af 100%) !important;
  color: #fff !important;
  border-color: #1a56db !important;
  box-shadow: 0 1px 4px rgba(26,86,219,.35) !important;
}
[data-testid="stButton"] button[kind="primary"]:hover {
  background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%) !important;
  box-shadow: 0 2px 8px rgba(26,86,219,.5) !important;
  transform: translateY(-1px) !important;
}
[data-testid="stButton"] button[kind="secondary"] {
  background: #161b22 !important;
  color: #cdd9e5 !important;
  border-color: #30363d !important;
}
[data-testid="stButton"] button[kind="secondary"]:hover {
  background: #1c2128 !important;
  border-color: #8b949e !important;
  color: #e6edf3 !important;
}

/* Download buttons */
[data-testid="stDownloadButton"] button {
  background: #161b22 !important;
  border: 1px solid #30363d !important;
  color: #8b949e !important;
  border-radius: 8px !important;
  font-size: 0.8rem !important;
}
[data-testid="stDownloadButton"] button:hover {
  background: #1c2128 !important;
  border-color: #8b949e !important;
  color: #cdd9e5 !important;
}

/* ── Expanders ────────────────────────────────────────────────────────────── */
[data-testid="stExpander"] {
  border: 1px solid #1e2530 !important;
  border-radius: 10px !important;
  background: #111827 !important;
  margin-bottom: 0.6rem !important;
  overflow: hidden !important;
}
[data-testid="stExpander"] details summary {
  padding: 0.8rem 1rem !important;
  font-weight: 500 !important;
  font-size: 0.9rem !important;
  color: #cdd9e5 !important;
}
[data-testid="stExpander"] details summary:hover { background: #161b22 !important; }
[data-testid="stExpander"] details[open] summary { border-bottom: 1px solid #1e2530 !important; }

/* ── Inputs ───────────────────────────────────────────────────────────────── */
[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea,
[data-testid="stNumberInput"] input {
  background: #0d1117 !important;
  border: 1px solid #30363d !important;
  border-radius: 8px !important;
  color: #e6edf3 !important;
  font-size: 0.875rem !important;
  transition: border-color 0.15s, box-shadow 0.15s !important;
}
[data-testid="stTextInput"] input:focus,
[data-testid="stTextArea"] textarea:focus,
[data-testid="stNumberInput"] input:focus {
  border-color: #1a56db !important;
  box-shadow: 0 0 0 3px rgba(26,86,219,.2) !important;
  outline: none !important;
}

/* ── Selectbox / Multiselect ──────────────────────────────────────────────── */
[data-testid="stSelectbox"] > div > div,
[data-testid="stMultiSelect"] > div > div {
  background: #0d1117 !important;
  border: 1px solid #30363d !important;
  border-radius: 8px !important;
  color: #e6edf3 !important;
}
[data-testid="stMultiSelect"] span[data-baseweb="tag"] {
  background: #1e3a5f !important;
  border: 1px solid #1a56db !important;
  border-radius: 4px !important;
}

/* ── Tabs ─────────────────────────────────────────────────────────────────── */
[data-testid="stTabs"] [data-baseweb="tab-list"] {
  background: transparent !important;
  border-bottom: 1px solid #1e2530 !important;
  gap: 4px !important;
  padding-bottom: 0 !important;
}
[data-testid="stTabs"] [data-baseweb="tab"] {
  background: transparent !important;
  color: #6e7681 !important;
  font-size: 0.85rem !important;
  font-weight: 500 !important;
  padding: 0.5rem 1rem !important;
  border-radius: 6px 6px 0 0 !important;
  border-bottom: 2px solid transparent !important;
  transition: color 0.15s !important;
}
[data-testid="stTabs"] [data-baseweb="tab"]:hover { color: #cdd9e5 !important; }
[data-testid="stTabs"] [aria-selected="true"] {
  color: #e6edf3 !important;
  border-bottom-color: #1a56db !important;
  background: #111827 !important;
}

/* ── Alerts ───────────────────────────────────────────────────────────────── */
[data-testid="stAlert"] {
  border-radius: 8px !important;
  font-size: 0.875rem !important;
  border-width: 1px !important;
  border-style: solid !important;
}

/* ── Dividers ─────────────────────────────────────────────────────────────── */
hr { border-color: #1e2530 !important; margin: 1.25rem 0 !important; }

/* ── Caption ──────────────────────────────────────────────────────────────── */
[data-testid="stCaptionContainer"] p {
  color: #6e7681 !important;
  font-size: 0.78rem !important;
}

/* ── Dataframe ────────────────────────────────────────────────────────────── */
[data-testid="stDataFrame"] {
  border: 1px solid #1e2530 !important;
  border-radius: 10px !important;
  overflow: hidden !important;
}

/* ── Toggle ───────────────────────────────────────────────────────────────── */
[data-testid="stToggle"] label { color: #cdd9e5 !important; font-size: 0.875rem !important; }

/* ── Scrollbar ────────────────────────────────────────────────────────────── */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: #0d1117; }
::-webkit-scrollbar-thumb { background: #30363d; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #8b949e; }
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
    if not st.session_state.get("logged_in"):
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

    # ── (Memória automática removida a pedido do usuário) ─────────────────────
    # ── Cruzamento automático global (roda em qualquer página) ────────────────
    if ("plan_df" in st.session_state and "assets_df" in st.session_state
            and "merged_df" not in st.session_state):
        _pdf = st.session_state["plan_df"]
        _adf = st.session_state["assets_df"]
        _avail = [f for f in TAXONOMY_JOIN_FIELDS
                  if f in _pdf.columns and f in _adf.columns]
        if _avail:
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
        _role_color = {"admin": "#f0883e", "editor": "#3fb950", "viewer": "#8b949e"}.get(role, "#8b949e")
        st.markdown(f"""
        <div style="padding:1.25rem 0.5rem 1rem;border-bottom:1px solid #1e2530;margin-bottom:0.75rem">
          <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
            <div style="width:36px;height:36px;background:linear-gradient(135deg,#1a56db,#1e40af);
                        border-radius:9px;display:flex;align-items:center;justify-content:center;
                        font-size:18px;flex-shrink:0">📊</div>
            <div>
              <div style="font-weight:700;font-size:0.95rem;color:#e6edf3;line-height:1.1">Campanhas PPG</div>
              <div style="font-size:0.7rem;color:#6e7681">Campaign Management</div>
            </div>
          </div>
          <div style="display:flex;align-items:center;gap:8px;background:#111827;
                      border:1px solid #1e2530;border-radius:8px;padding:6px 10px">
            <div style="width:26px;height:26px;background:#1e2530;border-radius:50%;
                        display:flex;align-items:center;justify-content:center;font-size:13px">👤</div>
            <div style="flex:1;min-width:0">
              <div style="font-size:0.8rem;font-weight:600;color:#cdd9e5;
                          white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{username}</div>
              <div style="font-size:0.68rem;font-weight:600;color:{_role_color};
                          text-transform:uppercase;letter-spacing:0.05em">{role}</div>
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        # Aviso de senha padrão (item 3)
        if has_default_password(username):
            st.warning("⚠️ Você está usando a senha padrão. Altere-a abaixo.", icon="🔒")

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
