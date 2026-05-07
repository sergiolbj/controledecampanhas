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
    if "_cm" not in st.session_state:
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


# ── Page header helper ────────────────────────────────────────────────────────
def _page_header(icon: str, title: str, subtitle: str = "") -> None:
    sub_html = f'<p style="margin:0;font-size:0.875rem;color:#6e7681">{subtitle}</p>' if subtitle else ""
    st.markdown(f"""
    <div style="display:flex;align-items:center;gap:14px;margin-bottom:1.75rem;
                padding-bottom:1.25rem;border-bottom:1px solid #1e2530">
      <div style="width:46px;height:46px;background:linear-gradient(135deg,#1a56db,#1e40af);
                  border-radius:12px;display:flex;align-items:center;justify-content:center;
                  font-size:22px;flex-shrink:0;box-shadow:0 2px 8px rgba(26,86,219,.35)">{icon}</div>
      <div>
        <h1 style="margin:0;font-size:1.5rem;font-weight:700;color:#e6edf3;letter-spacing:-0.02em">{title}</h1>
        {sub_html}
      </div>
    </div>
    """, unsafe_allow_html=True)


# ── Export helper ─────────────────────────────────────────────────────────────
def _export_buttons(df: pd.DataFrame, base_name: str, key: str) -> None:
    """Renderiza botões de download CSV e Excel lado a lado."""
    import io as _io
    ec1, ec2 = st.columns(2)
    ec1.download_button(
        "⬇️ Exportar CSV",
        df.to_csv(index=False).encode("utf-8"),
        f"{base_name}.csv", "text/csv",
        key=f"{key}_csv",
    )
    _buf = _io.BytesIO()
    with pd.ExcelWriter(_buf, engine="openpyxl") as _w:
        df.to_excel(_w, index=False, sheet_name="Dados")
    ec2.download_button(
        "⬇️ Exportar Excel",
        _buf.getvalue(),
        f"{base_name}.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=f"{key}_xlsx",
    )


# ── Template CRUD ─────────────────────────────────────────────────────────────
def save_template(client: str, name: str, source_type: str, mapping: dict) -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO mapping_templates
                (client_name, template_name, source_type, mapping_json) VALUES (%s,%s,%s,%s)
                ON CONFLICT (client_name, template_name) DO UPDATE SET
                    source_type = EXCLUDED.source_type,
                    mapping_json = EXCLUDED.mapping_json
            """, (client, name, source_type, json.dumps(mapping)))
    st.cache_data.clear()


@st.cache_data(ttl=60, show_spinner=False)
def load_templates(client: str) -> dict:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT template_name, source_type, mapping_json "
                "FROM mapping_templates WHERE client_name=%s",
                (client,),
            )
            rows = cur.fetchall()
    return {r[0]: {"source_type": r[1], "mapping": json.loads(r[2])} for r in rows}


# ── Dual Mapper UI ────────────────────────────────────────────────────────────
def mapper_ui(
    label: str, prefix: str, fields: list[str], role: str
) -> tuple[pd.DataFrame | None, dict, str, str, str, dict]:
    """File-loader + taxonomy mapper for one source. Returns (df, mapping, veh_col, veh_filter, source_info, config)."""
    st.subheader(f"📁 {label}")

    src = st.radio(
        "Origem",
        ["Upload de Arquivo", "Link (Google Sheets / Office 365)"],
        horizontal=True,
        key=f"{prefix}_src",
    )

    df: pd.DataFrame | None = None
    source_info = ""

    if src == "Upload de Arquivo":
        uploaded = st.file_uploader(
            "XLSX, XLS ou CSV", type=["xlsx", "xls", "csv"], key=f"{prefix}_file"
        )
        if uploaded:
            source_info = f"Arquivo: {uploaded.name}"
            is_excel = uploaded.name.lower().endswith((".xlsx", ".xls"))

            # Cache sheet list — re-detect only when file changes
            sheets_fp = (uploaded.name, uploaded.size)
            if st.session_state.get(f"{prefix}_sheets_fp") != sheets_fp:
                st.session_state[f"{prefix}_sheets_cache"] = get_sheets(uploaded) if is_excel else []
                st.session_state[f"{prefix}_sheets_fp"] = sheets_fp
            sheets = st.session_state.get(f"{prefix}_sheets_cache", [])

            sheet = (
                st.selectbox("Aba (Sheet)", sheets, key=f"{prefix}_sheet")
                if sheets else 0
            )
            hr1, hr2 = st.columns(2)
            h_start = hr1.number_input(
                "Cabeçalho — linha inicial", 1, 1000, 1, key=f"{prefix}_hrow_s",
                help="Número da linha onde ficam os nomes das colunas na planilha (normalmente 1). Use um valor maior se houver linhas de título antes do cabeçalho.",
            )
            h_end   = hr2.number_input(
                "Cabeçalho — linha final", int(h_start), 1000, int(h_start), key=f"{prefix}_hrow_e",
                help="Preencha só se o cabeçalho ocupar múltiplas linhas. Na maioria dos casos deve ser igual à linha inicial.",
            )
            header_row = list(range(int(h_start) - 1, int(h_end))) if h_end > h_start else int(h_start) - 1

            # Cache DataFrame — re-read only when file/sheet/header changes
            df_fp = (uploaded.name, uploaded.size, str(sheet), str(header_row))
            if st.session_state.get(f"{prefix}_df_fp") != df_fp:
                with st.spinner("Carregando arquivo..."):
                    try:
                        st.session_state[f"{prefix}_df_cache"] = read_file(
                            "upload", file_obj=uploaded,
                            sheet_name=sheet, header_row=header_row,
                        )
                        st.session_state[f"{prefix}_df_fp"] = df_fp
                    except Exception as e:
                        st.error(f"Erro ao ler arquivo: {e}")
            df = st.session_state.get(f"{prefix}_df_cache")
    else:
        url = st.text_input(
            "Link público", placeholder="https://docs.google.com/spreadsheets/...",
            key=f"{prefix}_url",
        )
        if url:
            source_info = f"Link: {url}"
            # Cache sheet detection — re-fetch only when URL changes
            if st.session_state.get(f"{prefix}_url_last") != url:
                with st.spinner("Detectando abas..."):
                    st.session_state[f"{prefix}_url_sheets"] = get_sheets_from_url(url)
                st.session_state[f"{prefix}_url_last"] = url

            url_sheets = st.session_state.get(f"{prefix}_url_sheets", [])
            sheet = (
                st.selectbox("Aba (Sheet)", url_sheets, key=f"{prefix}_sheet_url")
                if len(url_sheets) > 1 else (url_sheets[0] if url_sheets else 0)
            )
            ur1, ur2 = st.columns(2)
            h_start = ur1.number_input(
                "Cabeçalho — linha inicial", 1, 1000, 1, key=f"{prefix}_hrow_us",
                help="Número da linha onde ficam os nomes das colunas na planilha (normalmente 1). Use um valor maior se houver linhas de título antes do cabeçalho.",
            )
            h_end   = ur2.number_input(
                "Cabeçalho — linha final", int(h_start), 1000, int(h_start), key=f"{prefix}_hrow_ue",
                help="Preencha só se o cabeçalho ocupar múltiplas linhas. Na maioria dos casos deve ser igual à linha inicial.",
            )
            header_row = list(range(int(h_start) - 1, int(h_end))) if h_end > h_start else int(h_start) - 1

            # Cache DataFrame — re-fetch only when URL/sheet/header changes
            df_fp = (url, str(sheet), str(header_row))
            if st.session_state.get(f"{prefix}_df_fp") != df_fp:
                with st.spinner("Carregando dados..."):
                    try:
                        st.session_state[f"{prefix}_df_cache"] = read_file(
                            "url", url=url, sheet_name=sheet, header_row=header_row,
                        )
                        st.session_state[f"{prefix}_df_fp"] = df_fp
                    except Exception as e:
                        st.error(f"Erro ao carregar link: {e}")
            df = st.session_state.get(f"{prefix}_df_cache")

    mapping: dict[str, str] = {}

    if df is not None:
        st.success(f"✅ {len(df):,} linhas · {len(df.columns)} colunas carregadas")
        with st.expander("Prévia dos dados", expanded=False):
            st.dataframe(df.head(8), use_container_width=True)

        # ── Templates (carregar e salvar no mesmo expander) ───────────────────
        if role == "admin":
            with st.expander("📂 Templates de mapeamento", expanded=False):
                clients_list = get_clients()
                tpl_client = st.selectbox(
                    "Cliente", ["—"] + clients_list, key=f"{prefix}_cli"
                )

                # ── Carregar ──────────────────────────────────────────────
                st.markdown("**Carregar template**")
                if tpl_client != "—":
                    templates = load_templates(tpl_client)
                    if templates:
                        tl1, tl2 = st.columns([4, 1])
                        sel_tpl = tl1.selectbox(
                            "Template salvo", ["—"] + list(templates.keys()),
                            key=f"{prefix}_tload",
                        )
                        tl2.write(""); tl2.write("")
                        if tl2.button("📂 Aplicar", key=f"{prefix}_tapply"):
                            if sel_tpl != "—":
                                tpl_map = templates[sel_tpl]["mapping"]
                                cols_available = ["(não mapear)"] + list(df.columns)
                                missing_cols = [
                                    col_val for col_val in tpl_map.values()
                                    if col_val and col_val != "(não mapear)" and col_val not in cols_available
                                ]
                                if missing_cols:
                                    st.warning(
                                        f"⚠️ {len(missing_cols)} campo(s) deste template não existem nesta planilha: "
                                        + ", ".join(f"`{c}`" for c in missing_cols)
                                        + ". Esses campos serão ignorados."
                                    )
                                for field, col_val in tpl_map.items():
                                    st.session_state[f"{prefix}_{field}"] = (
                                        col_val if col_val in cols_available else "(não mapear)"
                                    )
                                st.session_state[f"{prefix}_loaded_map"]  = tpl_map
                                st.session_state[f"{prefix}_loaded_name"] = sel_tpl
                                st.rerun()
                            else:
                                st.warning("Selecione um template.")
                    else:
                        st.caption("Nenhum template salvo para este cliente.")
                else:
                    st.caption("Selecione um cliente para ver os templates disponíveis.")

                # ── Salvar ────────────────────────────────────────────────
                st.markdown("**Salvar mapeamento atual como template**")
                sv1, sv2 = st.columns([4, 1])
                tpl_name = sv1.text_input(
                    "Nome do template",
                    placeholder="Ex: Plano Google Ads",
                    key=f"{prefix}_tname",
                )
                sv2.write(""); sv2.write("")
                if sv2.button("💾 Salvar", type="primary", key=f"{prefix}_tsave"):
                    if tpl_client != "—" and tpl_name.strip():
                        save_template(tpl_client, tpl_name.strip(), src, mapping)
                        st.success(f"✅ Template **{tpl_name}** salvo para **{tpl_client}**!")
                    else:
                        st.warning("Selecione um cliente e informe o nome do template.")

            # Badge do template ativo + botão para limpar
            loaded_name = st.session_state.get(f"{prefix}_loaded_name")
            if loaded_name:
                bn1, bn2 = st.columns([5, 1])
                bn1.caption(f"📋 Template ativo: **{loaded_name}**")
                if bn2.button("✖ Limpar", key=f"{prefix}_tclear"):
                    for field in fields:
                        st.session_state.pop(f"{prefix}_{field}", None)
                    st.session_state.pop(f"{prefix}_loaded_map",  None)
                    st.session_state.pop(f"{prefix}_loaded_name", None)
                    st.rerun()

        # ── Mapeamento de Taxonomia ────────────────────────────────────────────
        loaded_map = st.session_state.get(f"{prefix}_loaded_map", {})
        st.markdown("##### Mapeamento de Taxonomia")
        st.caption("Selecione a coluna correspondente a cada campo. Escolha **(não mapear)** para ignorar campos que não existem na sua planilha.")
        cols_opt = ["(não mapear)"] + list(df.columns)
        c1, c2 = st.columns(2)

        for i, field in enumerate(fields):
            # Prioridade: template carregado > auto-guess
            if field in loaded_map and loaded_map[field] in cols_opt:
                idx = cols_opt.index(loaded_map[field])
            else:
                kw = field.replace("_", "").lower()
                guess = next(
                    (c for c in df.columns
                     if kw in str(c).lower().replace(" ", "").replace("_", "")),
                    "(não mapear)",
                )
                idx = cols_opt.index(guess) if guess in cols_opt else 0
            with (c1 if i % 2 == 0 else c2):
                mapping[field] = st.selectbox(
                    FIELD_LABELS.get(field, field),
                    cols_opt, index=idx, key=f"{prefix}_{field}",
                )

        # ── Filtro por Veículo ────────────────────────────────────────────────
        st.markdown("---")
        st.markdown("##### Filtro por Veículo")
        vf1, vf2 = st.columns(2)
        veh_col = vf1.selectbox(
            "Coluna que identifica o Veículo",
            ["(não usar)"] + list(df.columns),
            key=f"{prefix}_veh_col",
        )
        veh_filter = vf2.text_input(
            "Filtrar por valor de Veículo",
            placeholder="Ex: Google Ads  (vazio = carregar todos)",
            key=f"{prefix}_veh_filter",
        )
        if veh_col != "(não usar)" and veh_filter.strip():
            n = (df[veh_col].astype(str).str.strip().str.lower()
                 == veh_filter.strip().lower()).sum()
            st.caption(f"🔍 Prévia: **{n:,}** de **{len(df):,}** linhas correspondem ao filtro")


    else:
        veh_col    = "(não usar)"
        veh_filter = ""

    config = {
        "src": src,
        "sheet": sheet if 'sheet' in locals() else 0,
        "header_row": header_row if 'header_row' in locals() else 0,
        "veh_col": veh_col,
        "veh_filter": veh_filter,
    }
    if src != "Upload de Arquivo":
        config["url"] = st.session_state.get(f"{prefix}_url")

    return df, mapping, veh_col, veh_filter, source_info, config


# ── Gantt chart ───────────────────────────────────────────────────────────────
def gantt_chart(df: pd.DataFrame) -> None:
    need = {"vehicle", "start_date", "end_date"}
    if not need.issubset(df.columns):
        st.warning(f"Colunas ausentes para o Gantt: {need - set(df.columns)}")
        return

    plot = df.dropna(subset=["start_date", "end_date"]).copy()
    plot["start_date"] = pd.to_datetime(plot["start_date"], errors="coerce")
    plot["end_date"]   = pd.to_datetime(plot["end_date"],   errors="coerce")
    plot = plot.dropna(subset=["start_date", "end_date"])

    if plot.empty:
        st.info("Sem datas válidas para renderizar o Gantt.")
        return

    if "sys_campaign" in plot.columns:
        base_y = plot["sys_campaign"].astype(str)
    elif "campaign_name" in plot.columns:
        base_y = plot["campaign_name"].astype(str)
    else:
        base_y = pd.Series("Campanha", index=plot.index)

    # Use sys_vehicle identity column when available — it is stamped pre-merge
    # and cannot be contaminated by the fuzzy join
    _veh_col = "sys_vehicle" if "sys_vehicle" in plot.columns else "vehicle"

    # Use a compound row label to separate vehicles into distinct rows
    plot["row_label"] = base_y.str.strip() + "  ·  " + plot[_veh_col].astype(str).str.strip()

    # Sort to ensure consistent ordering
    plot = plot.sort_values(by=["row_label"]).reset_index(drop=True)
    row_labels_ordered = plot["row_label"].unique().tolist()
    y_col = "row_label"

    hover_cols = [
        c for c in ["sys_campaign", "sys_vehicle", "campaign_name", "asset_id", "format", "status", "asset_link"]
        if c in plot.columns
    ]

    fig = px.timeline(
        plot,
        x_start="start_date",
        x_end="end_date",
        y=y_col,
        color=_veh_col,
        text=_veh_col,
        hover_data={c: True for c in hover_cols},
        color_discrete_sequence=px.colors.qualitative.Dark24,
        labels={c: FIELD_LABELS.get(c, c) for c in plot.columns},
        title="📅 Timeline de Veiculação",
    )
    fig.update_yaxes(
        autorange="reversed", 
        title="Campanhas",
        categoryorder="array", 
        categoryarray=row_labels_ordered,
        tickfont=dict(size=12, color="#c9d1d9")
    )
    fig.update_xaxes(title="")
    fig.update_traces(textposition="inside", insidetextanchor="middle")
    
    n_bars = len(plot[["campaign_name", "vehicle"]].drop_duplicates())
    fig.update_layout(
        plot_bgcolor  = "#0d1117",
        paper_bgcolor = "#0d1117",
        font_color    = "#c9d1d9",
        height        = max(450, n_bars * 40 + 180),
        legend_title  = "Veículo",
        xaxis         = dict(showgrid=True, gridcolor="#21262d"),
        yaxis         = dict(showgrid=False),
        margin        = dict(l=10, r=10, t=50, b=10),
    )
    st.plotly_chart(fig, use_container_width=True)


# ── Duplicate vehicle helper ──────────────────────────────────────────────────
def _copy_ingestion(
    src_camp_id: int, src_veh_id: int,
    dst_camp_id: int, dst_veh_id: int,
    dtype: str, new_url: str | None,
    src_cfg: dict, src_map: dict,
) -> str:
    """Copy one ingestion_cache entry to a new campaign/vehicle.

    If new_url is given and the source is Sheets-based, re-fetches from the
    new URL applying the exact same sheet/mapping/filter config.
    Otherwise copies the existing blob as-is.

    Returns a human-readable summary string.
    """
    uses_sheets = "Sheets" in src_cfg.get("src", "") or "Office" in src_cfg.get("src", "")

    if new_url and uses_sheets:
        cfg = {**src_cfg, "url": new_url}
        df = read_file(
            "url", url=new_url,
            sheet_name=src_cfg.get("sheet", 0),
            header_row=src_cfg.get("header_row", 0),
        )
        if df is None or df.empty:
            raise ValueError(f"Planilha vazia ou inacessível: {new_url}")

        veh_col    = src_cfg.get("veh_col", "(não usar)")
        veh_filter = src_cfg.get("veh_filter", "")
        if veh_col != "(não usar)" and veh_filter.strip():
            mask = (
                df[veh_col].astype(str).str.strip().str.lower()
                == veh_filter.strip().lower()
            )
            df = df[mask].copy()
        if veh_col != "(não usar)" and veh_col in df.columns:
            df = df.drop(columns=[veh_col])

        active = {k: v for k, v in src_map.items() if v != "(não mapear)"}
        if dtype == "plan":
            df = normalize_dates(apply_mapping(df, active), ["start_date", "end_date"])
        else:
            df = apply_mapping(df, active)

        _dup_user = st.session_state.get("username", "")
        save_ingestion(dst_camp_id, dst_veh_id, dtype, df, src_map,
                       f"Duplicado de camp={src_camp_id} veh={src_veh_id}", json.dumps(cfg),
                       username=_dup_user)
        return f"{len(df):,} linhas importadas do novo link"
    else:
        # Copy existing blob
        df_src, map_src, _, src_info, _ = load_ingestion(src_camp_id, src_veh_id, dtype)
        if df_src is None or df_src.empty:
            return "sem dados na origem — pulado"
        _dup_user = st.session_state.get("username", "")
        save_ingestion(dst_camp_id, dst_veh_id, dtype, df_src, map_src,
                       f"Duplicado de camp={src_camp_id} veh={src_veh_id}", json.dumps(src_cfg),
                       username=_dup_user)
        return f"{len(df_src):,} linhas copiadas"


def _duplicate_vehicle_ui(username: str, role: str) -> None:
    with st.expander("📋 Duplicar configuração de veículo", expanded=False):
        st.caption(
            "Copie toda a configuração de um veículo (mapeamento de colunas, aba, filtros) "
            "para uma nova campanha — troque apenas o link da planilha."
        )

        all_camps = get_campaigns(username, role)
        if not all_camps:
            st.info("Nenhuma campanha disponível.")
            return

        camp_names = [c["name"] for c in all_camps]

        # ── Origem ────────────────────────────────────────────────────────────
        st.markdown("**Origem**")
        c1, c2 = st.columns(2)
        src_camp_name = c1.selectbox("Campanha", camp_names, key="dup_src_camp")
        src_camp      = next(c for c in all_camps if c["name"] == src_camp_name)
        src_vehs      = get_vehicles(src_camp["id"])

        if not src_vehs:
            st.warning("Nenhum veículo configurado nessa campanha.")
            return

        src_veh_name = c2.selectbox("Veículo", [v["name"] for v in src_vehs], key="dup_src_veh")
        src_veh      = next(v for v in src_vehs if v["name"] == src_veh_name)

        _, plan_map, _, _, plan_cfg  = load_ingestion(src_camp["id"], src_veh["id"], "plan")
        _, ast_map,  _, _, ast_cfg   = load_ingestion(src_camp["id"], src_veh["id"], "assets")
        src_plan_url   = (plan_cfg  or {}).get("url", "")
        src_assets_url = (ast_cfg   or {}).get("url", "")

        # ── Destino ───────────────────────────────────────────────────────────
        st.divider()
        st.markdown("**Destino**")
        d1, d2 = st.columns(2)

        use_new = d1.toggle("Criar nova campanha", value=True, key="dup_new_camp_toggle")
        if use_new:
            dst_camp_name   = d1.text_input("Nome da nova campanha", key="dup_new_camp_name")
            dst_client      = d1.text_input(
                "Cliente", value=src_camp.get("client_name", ""), key="dup_new_client"
            )
        else:
            dst_camp_sel = d1.selectbox("Campanha existente", camp_names, key="dup_exist_camp")

        dst_veh_name = d2.text_input("Nome do veículo", value=src_veh_name, key="dup_dst_veh")

        # ── Novos links ───────────────────────────────────────────────────────
        st.divider()
        st.markdown("**Planilhas** — deixe em branco para usar o mesmo link da origem")
        u1, u2 = st.columns(2)

        def _short(url: str) -> str:
            return (url[:70] + "…") if len(url) > 70 else url

        new_plan_url = u1.text_input(
            "URL do Plano",
            placeholder=_short(src_plan_url) if src_plan_url else "mesmo link da origem",
            key="dup_new_plan_url",
        )
        new_assets_url = u2.text_input(
            "URL dos Assets",
            placeholder=_short(src_assets_url) if src_assets_url else "mesmo link da origem",
            key="dup_new_assets_url",
        )

        st.divider()
        if st.button("✅ Criar cópia", type="primary", key="dup_btn_create"):
            if not dst_veh_name.strip():
                st.error("Informe o nome do veículo destino.")
                return

            with st.spinner("Criando cópia..."):
                try:
                    # Resolve destination campaign
                    if use_new:
                        if not dst_camp_name.strip():
                            st.error("Informe o nome da nova campanha.")
                            return
                        existing = next(
                            (c for c in all_camps if c["name"] == dst_camp_name.strip()), None
                        )
                        dst_camp_id = (
                            existing["id"] if existing
                            else create_campaign(dst_camp_name.strip(), dst_client.strip())
                        )
                        resolved_camp_name = dst_camp_name.strip()
                    else:
                        dst_obj = next(c for c in all_camps if c["name"] == dst_camp_sel)
                        dst_camp_id        = dst_obj["id"]
                        resolved_camp_name = dst_obj["name"]

                    # Resolve destination vehicle
                    dst_vehs     = get_vehicles(dst_camp_id)
                    existing_veh = next(
                        (v for v in dst_vehs if v["name"] == dst_veh_name.strip()), None
                    )
                    if existing_veh:
                        dst_veh_id = existing_veh["id"]
                        st.warning(
                            f"Veículo '{dst_veh_name}' já existe em '{resolved_camp_name}' "
                            "— configuração sobrescrita."
                        )
                    else:
                        dst_veh_id = create_vehicle(dst_camp_id, dst_veh_name.strip())

                    # Copy plan
                    plan_summary = _copy_ingestion(
                        src_camp["id"], src_veh["id"],
                        dst_camp_id, dst_veh_id,
                        "plan",
                        new_plan_url.strip() or None,
                        plan_cfg or {}, plan_map or {},
                    )

                    # Copy assets
                    assets_summary = _copy_ingestion(
                        src_camp["id"], src_veh["id"],
                        dst_camp_id, dst_veh_id,
                        "assets",
                        new_assets_url.strip() or None,
                        ast_cfg or {}, ast_map or {},
                    )

                    st.success(
                        f"Cópia criada com sucesso!\n\n"
                        f"**{resolved_camp_name} › {dst_veh_name.strip()}**\n\n"
                        f"- Plano: {plan_summary}\n"
                        f"- Assets: {assets_summary}"
                    )

                    if st.button(
                        f"Abrir {dst_veh_name.strip()} →",
                        key="dup_goto_new",
                    ):
                        st.session_state.update(
                            cfg_campaign_id=dst_camp_id,
                            cfg_campaign_name=resolved_camp_name,
                            cfg_vehicle_id=dst_veh_id,
                            cfg_vehicle_name=dst_veh_name.strip(),
                        )
                        for k in ["plan_df", "assets_df", "merged_df",
                                  "unmatched_df", "fuzzy_df", "_cross_sig"]:
                            st.session_state.pop(k, None)
                        st.rerun()

                except Exception as exc:
                    st.error(f"Erro ao criar cópia: {exc}")


# ── Wizard helpers ────────────────────────────────────────────────────────────
def _step_bar(current: int) -> None:
    labels = ["1 · Campanha", "2 · Veículo", "3 · Mapeamento"]
    cols = st.columns(3)
    for i, (col, label) in enumerate(zip(cols, labels)):
        n = i + 1
        if n < current:
            col.markdown(f"<div style='text-align:center;color:#3fb950'>✅ {label}</div>", unsafe_allow_html=True)
        elif n == current:
            col.markdown(f"<div style='text-align:center;color:#58a6ff;font-weight:700'>● {label}</div>", unsafe_allow_html=True)
        else:
            col.markdown(f"<div style='text-align:center;color:#484f58'>○ {label}</div>", unsafe_allow_html=True)


def _step_campaign() -> None:
    username = st.session_state.get("username")
    role     = st.session_state.get("role")
    campaigns = get_campaigns(username=username, role=role)
    st.subheader("Campanha")
    mode = st.radio("", ["Selecionar existente", "Criar nova"],
                    horizontal=True, key="camp_mode")

    if mode == "Criar nova":
        nc1, nc2 = st.columns(2)
        name        = nc1.text_input("Nome da nova campanha", key="camp_new")
        clients     = get_clients()
        client_name = nc2.selectbox("Cliente", ["(Nenhum)"] + clients, key="camp_client")
        if st.button("Criar e continuar →", type="primary", key="camp_create"):
            if name.strip():
                try:
                    final_client = "" if client_name == "(Nenhum)" else client_name
                    cid = create_campaign(name.strip(), final_client)
                    st.session_state.update(cfg_campaign_id=cid, cfg_campaign_name=name.strip())
                    st.rerun()
                except Exception as e:
                    st.error("Já existe uma campanha com esse nome." if "UNIQUE" in str(e) else str(e))
            else:
                st.warning("Informe o nome da campanha.")
    else:
        if not campaigns:
            st.info("Nenhuma campanha cadastrada ainda. Selecione **Criar nova**.")
        else:
            opts     = {c["name"]: c["id"] for c in campaigns}
            clients_map  = {c["name"]: c.get("client_name", "") for c in campaigns}
            sel = st.selectbox(
                "Selecione a campanha",
                list(opts.keys()),
                format_func=lambda n: f"[{clients_map[n]}] {n}" if clients_map.get(n) else n,
                key="camp_sel",
            )
            
            all_clients = get_clients()
            current_client = clients_map[sel]
            idx = all_clients.index(current_client) + 1 if current_client in all_clients else 0
            new_cli = st.selectbox("Cliente associado", ["(Nenhum)"] + all_clients, index=idx, key="camp_edit_cli")
            
            if st.button("Continuar →", type="primary", key="camp_select"):
                final_cli = "" if new_cli == "(Nenhum)" else new_cli
                if final_cli != current_client:
                    update_campaign_client(opts[sel], final_cli)
                st.session_state.update(cfg_campaign_id=opts[sel], cfg_campaign_name=sel)
                st.rerun()


def _step_vehicle() -> None:
    camp_name = st.session_state["cfg_campaign_name"]
    camp_id   = st.session_state["cfg_campaign_id"]

    c1, c2 = st.columns([5, 1])
    c1.caption(f"📢 Campanha: **{camp_name}**")
    if c2.button("← Alterar", key="back_camp"):
        st.session_state.pop("cfg_campaign_id", None)
        st.session_state.pop("cfg_campaign_name", None)
        st.rerun()

    st.subheader("Veículo")
    vehicles = get_vehicles(camp_id)
    mode = st.radio("", ["Selecionar existente", "Criar novo"],
                    horizontal=True, key="veh_mode")

    def _confirm_vehicle(vid: int, vname: str) -> None:
        save_user_state(st.session_state["username"], camp_id, vid)
        update = {"cfg_vehicle_id": vid, "cfg_vehicle_name": vname}
        for dtype, df_key, map_key, src_key, cfg_key in [
            ("plan",   "plan_df",   "plan_mapping", "plan_source", "plan_config"),
            ("assets", "assets_df", "assets_mapping", "assets_source", "assets_config"),
        ]:
            df, mapping, _, src_info, config = load_ingestion(camp_id, vid, dtype)
            if df is not None:
                update[df_key]  = df
                update[map_key] = mapping
                update[src_key] = src_info
                update[cfg_key] = config
        st.session_state.update(update)
        st.rerun()

    if mode == "Criar novo":
        name = st.text_input("Nome do novo veículo", key="veh_new")
        if st.button("Criar e continuar →", type="primary", key="veh_create"):
            if name.strip():
                try:
                    vid = create_vehicle(camp_id, name.strip())
                    _confirm_vehicle(vid, name.strip())
                except Exception as e:
                    st.error("Veículo já existe nesta campanha." if "UNIQUE" in str(e) else str(e))
            else:
                st.warning("Informe o nome do veículo.")
    else:
        if not vehicles:
            st.info("Nenhum veículo cadastrado para esta campanha. Selecione **Criar novo**.")
        else:
            opts = {v["name"]: v["id"] for v in vehicles}
            sel = st.selectbox("Selecione o veículo", list(opts.keys()), key="veh_sel")
            if st.button("Continuar →", type="primary", key="veh_select"):
                _confirm_vehicle(opts[sel], sel)


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════════
def main() -> None:
    init_db()

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
                        st.success("Senha alterada com sucesso!")
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

    # ═══════════════════════════════════════════════════════════════════════════
    #  PAGE 1 — MAPEAMENTO
    # ═══════════════════════════════════════════════════════════════════════════
    if page == "📥 Mapeamento & Cruzamento":
        _page_header("📥", "Mapeamento & Cruzamento", "Faça upload, mapeie colunas e cruze plano com assets")

        if role not in ["admin", "editor"]:
            st.warning("🔒 Somente administradores ou editores podem ingerir dados.")
            return

        # ── Wizard step indicator ─────────────────────────────────────────────
        has_campaign = "cfg_campaign_id" in st.session_state
        has_vehicle  = "cfg_vehicle_id"  in st.session_state
        step = 3 if (has_campaign and has_vehicle) else (2 if has_campaign else 1)

        _step_bar(step)

        # ── Duplicar veículo (item 6: visível logo abaixo do step bar) ────────
        if step == 1:
            _duplicate_vehicle_ui(username, role)

        st.divider()

        # ── Step 1 — Campanha ─────────────────────────────────────────────────
        if step == 1:
            _step_campaign()

        # ── Step 2 — Veículo ──────────────────────────────────────────────────
        elif step == 2:
            _step_vehicle()

        # ── Step 3 — Mapeamento ───────────────────────────────────────────────
        else:
            camp_id = st.session_state.get("cfg_campaign_id")
            veh_id  = st.session_state.get("cfg_vehicle_id")
            camp_name = st.session_state.get("cfg_campaign_name")
            veh_name  = st.session_state.get("cfg_vehicle_name")
            
            if not camp_name or not veh_name:
                camps = get_campaigns(username, role)
                for c in camps:
                    if c["id"] == camp_id:
                        camp_name = c["name"]
                        st.session_state["cfg_campaign_name"] = camp_name
                vehs = get_vehicles(camp_id)
                for v in vehs:
                    if v["id"] == veh_id:
                        veh_name = v["name"]
                        st.session_state["cfg_vehicle_name"] = veh_name
            
            camp_name = camp_name or "Campanha"
            veh_name = veh_name or "Veículo"

            b1, b2 = st.columns([5, 1])
            _ts = get_ingestion_timestamps(camp_id, veh_id)
            def _fmt_ts(ts, by: str) -> str:
                if ts is None:
                    return "nunca salvo"
                s = ts.strftime("%d/%m/%Y %H:%M") if hasattr(ts, "strftime") else str(ts)[:16]
                return f"{s} por **{by}**" if by else s
            b1.caption(
                f"📢 **{camp_name}** › 📺 **{veh_name}**  ·  "
                f"Plano: {_fmt_ts(_ts['plan'], _ts['plan_by'])}  ·  "
                f"Assets: {_fmt_ts(_ts['assets'], _ts['assets_by'])}"
            )
            if b2.button("← Alterar veículo", key="back_veh"):
                has_data = "plan_df" in st.session_state or "assets_df" in st.session_state
                if has_data:
                    st.session_state["_confirm_back_veh"] = True
                else:
                    for k in ["cfg_vehicle_id", "cfg_vehicle_name",
                               "plan_df", "assets_df", "merged_df", "unmatched_df", "fuzzy_df"]:
                        st.session_state.pop(k, None)
                    st.rerun()

            if st.session_state.get("_confirm_back_veh"):
                st.warning("⚠️ Ao voltar, os dados carregados serão descartados. Deseja continuar?")
                conf1, conf2 = st.columns(2)
                if conf1.button("✅ Sim, voltar", key="confirm_back_yes"):
                    for k in ["cfg_vehicle_id", "cfg_vehicle_name", "_confirm_back_veh",
                               "plan_df", "assets_df", "merged_df", "unmatched_df", "fuzzy_df"]:
                        st.session_state.pop(k, None)
                    st.rerun()
                if conf2.button("❌ Cancelar", key="confirm_back_no"):
                    st.session_state.pop("_confirm_back_veh", None)
                    st.rerun()

            tab_plan, tab_assets = st.tabs(["📋 Plano de Conteúdo", "🎨 Base de Assets"])

            with tab_plan:
                if st.session_state.get("plan_source"):
                    st.info(f"💾 Origem salva: **{st.session_state['plan_source']}**")
                plan_df, plan_map, veh_col, veh_filter, plan_source, plan_config = mapper_ui(
                    "Plano de Conteúdo", "plan", PLAN_FIELDS, role
                )
                if plan_df is not None:
                    if st.button("👁 Pré-visualizar mapeamento", key="preview_plan"):
                        active = {k: v for k, v in plan_map.items() if v != "(não mapear)"}
                        _prev = plan_df.copy()
                        if veh_col != "(não usar)" and veh_filter.strip():
                            _prev = _prev[_prev[veh_col].astype(str).str.strip().str.lower() == veh_filter.strip().lower()].copy()
                        if veh_col != "(não usar)" and veh_col in _prev.columns:
                            _prev = _prev.rename(columns={veh_col: "vehicle"})
                        _prev = normalize_dates(apply_mapping(_prev, active), ["start_date", "end_date"])
                        missing_fields = []
                        if "ad_name"     not in active: missing_fields.append("Nome do Anúncio")
                        if "start_date"  not in active: missing_fields.append("Data de Início")
                        if "end_date"    not in active: missing_fields.append("Data de Fim")
                        st.session_state["_plan_preview"] = {
                            "df": _prev, "missing": missing_fields,
                            "source": plan_source, "config": plan_config, "mapping": plan_map,
                        }

                    _prev_data = st.session_state.get("_plan_preview")
                    if _prev_data is not None:
                        if _prev_data["missing"]:
                            st.warning(
                                f"⚠️ Campo(s) importante(s) não mapeado(s): **{', '.join(_prev_data['missing'])}**. "
                                "O cruzamento pode ficar incompleto."
                            )
                        st.caption(f"Prévia — **{len(_prev_data['df']):,}** linhas após mapeamento:")
                        st.dataframe(_prev_data["df"].head(8), use_container_width=True, hide_index=True)
                        pc1, pc2 = st.columns(2)
                        if pc1.button("✅ Confirmar e Salvar Plano", type="primary", key="confirm_plan_save"):
                            mapped = _prev_data["df"]
                            st.session_state["plan_df"]      = mapped
                            st.session_state["plan_mapping"] = _prev_data["mapping"]
                            st.session_state["plan_source"]  = _prev_data["source"]
                            st.session_state["plan_config"]  = _prev_data["config"]
                            save_ingestion(
                                st.session_state["cfg_campaign_id"],
                                st.session_state["cfg_vehicle_id"],
                                "plan", mapped, _prev_data["mapping"],
                                _prev_data["source"], json.dumps(_prev_data["config"]),
                                username=username,
                            )
                            st.session_state.pop("_plan_preview", None)
                            st.success(f"✅ Plano confirmado e salvo: {len(mapped):,} registros.")
                            st.info("💡 Agora confirme os **Assets** para o cruzamento rodar automaticamente.")
                        if pc2.button("❌ Cancelar", key="cancel_plan_preview"):
                            st.session_state.pop("_plan_preview", None)
                            st.rerun()

            with tab_assets:
                if st.session_state.get("assets_source"):
                    st.info(f"💾 Origem salva: **{st.session_state['assets_source']}**")
                assets_df, assets_map, _, _, assets_source, assets_config = mapper_ui(
                    "Base de Assets", "assets", ASSET_FIELDS, role
                )
                if assets_df is not None:
                    if st.button("👁 Pré-visualizar mapeamento", key="preview_assets"):
                        active = {k: v for k, v in assets_map.items() if v != "(não mapear)"}
                        _prev_a = apply_mapping(assets_df.copy(), active)
                        missing_fields_a = []
                        if "asset_id"   not in active: missing_fields_a.append("ID do Asset")
                        if "asset_link" not in active: missing_fields_a.append("Link do Asset")
                        st.session_state["_assets_preview"] = {
                            "df": _prev_a, "missing": missing_fields_a,
                            "source": assets_source, "config": assets_config, "mapping": assets_map,
                        }

                    _prev_a_data = st.session_state.get("_assets_preview")
                    if _prev_a_data is not None:
                        if _prev_a_data["missing"]:
                            st.warning(
                                f"⚠️ Campo(s) importante(s) não mapeado(s): **{', '.join(_prev_a_data['missing'])}**. "
                                "O cruzamento pode ficar incompleto."
                            )
                        st.caption(f"Prévia — **{len(_prev_a_data['df']):,}** linhas após mapeamento:")
                        st.dataframe(_prev_a_data["df"].head(8), use_container_width=True, hide_index=True)
                        ac1, ac2 = st.columns(2)
                        if ac1.button("✅ Confirmar e Salvar Assets", type="primary", key="confirm_assets_save"):
                            mapped_a = _prev_a_data["df"]
                            st.session_state["assets_df"]      = mapped_a
                            st.session_state["assets_mapping"] = _prev_a_data["mapping"]
                            st.session_state["assets_source"]  = _prev_a_data["source"]
                            st.session_state["assets_config"]  = _prev_a_data["config"]
                            save_ingestion(
                                st.session_state["cfg_campaign_id"],
                                st.session_state["cfg_vehicle_id"],
                                "assets", mapped_a, _prev_a_data["mapping"],
                                _prev_a_data["source"], json.dumps(_prev_a_data["config"]),
                                username=username,
                            )
                            st.session_state.pop("_assets_preview", None)
                            st.success(f"✅ Assets confirmados e salvos: {len(mapped_a):,} registros. O cruzamento será recalculado automaticamente.")
                        if ac2.button("❌ Cancelar", key="cancel_assets_preview"):
                            st.session_state.pop("_assets_preview", None)
                            st.rerun()

            # ── Cruzamento automático ─────────────────────────────────────────
            plan_loaded   = "plan_df" in st.session_state
            assets_loaded = "assets_df" in st.session_state

            if plan_loaded and assets_loaded:
                st.divider()
                st.subheader("🔗 Cruzamento & Qualidade")

                plan_df_x   = st.session_state["plan_df"]
                assets_df_x = st.session_state["assets_df"]
                available   = [f for f in TAXONOMY_JOIN_FIELDS
                               if f in plan_df_x.columns and f in assets_df_x.columns]

                if not available:
                    st.warning("Mapeie **Nome da Campanha**, **Grupo de Anúncio** ou **Anúncio** em ambas as bases para habilitar o cruzamento.")
                else:
                    cx1, cx2, cx3 = st.columns([3, 2, 2])
                    fuzzy_threshold = cx1.slider(
                        "Threshold Fuzzy (%)", 50, 100, 80, key="auto_thresh",
                        help="Porcentagem mínima de similaridade para considerar dois nomes como correspondentes. Valores altos exigem maior semelhança; valores baixos aceitam correspondências mais distantes.",
                    )
                    use_fuzzy_merge = cx2.checkbox(
                        "🔀 Correspondência fuzzy", value=True, key="auto_fuzzy",
                        help="Quando ativado, tenta casar nomes de campanhas/grupos mesmo com pequenas diferenças de escrita. Desative para usar apenas correspondência exata.",
                    )

                    cx3.write("")
                    if cx3.button("🔄 Salvar e Recalcular", type="primary", key="btn_recalc_cross"):
                        for k in ["plan_df_fp", "plan_df_cache", "plan_url_last", 
                                  "assets_df_fp", "assets_df_cache", "assets_url_last",
                                  "_cross_sig", "merged_df", "unmatched_df", "fuzzy_df"]:
                            st.session_state.pop(k, None)
                        st.rerun()

                    cross_sig = (id(plan_df_x), id(assets_df_x),
                                 fuzzy_threshold, use_fuzzy_merge)
                    if st.session_state.get("_cross_sig") != cross_sig:
                        with st.spinner("Cruzando dados..."):
                            assets_agg = aggregate_assets(assets_df_x, available)
                            if use_fuzzy_merge:
                                matched, unmatched = fuzzy_merge_taxonomy(
                                    plan_df_x, assets_agg, available, fuzzy_threshold)
                            else:
                                matched, unmatched = merge_taxonomy(
                                    plan_df_x, assets_agg, available)
                            matched  = compute_veiculacao_status(matched)
                            fuzzy_rp = fuzzy_taxonomy_report(
                                plan_df_x, assets_agg, available, fuzzy_threshold)
                        st.session_state.update(
                            merged_df=matched, unmatched_df=unmatched,
                            fuzzy_df=fuzzy_rp, _cross_sig=cross_sig)

                    COL_LABELS = {
                        "veiculacao_status": "Status",
                        "_match_type":       "Match",
                        "vehicle":           "Veículo",
                        "campaign_name":     "Campanha",
                        "ad_group":          "Grupo de Anúncio",
                        "ad_name":           "Anúncio",
                        "start_date":        "Início Plano",
                        "end_date":          "Fim Plano",
                        "date":              "Última Veiculação",
                        "impressions":       "Impressões",
                        "clicks":            "Cliques",
                        "views":             "Views",
                        "spend":             "Valor Gasto (R$)",
                    }

                    def _reorder(df: pd.DataFrame) -> pd.DataFrame:
                        ordered = [c for c in COL_LABELS if c in df.columns]
                        rest    = [c for c in df.columns if c not in ordered]
                        return df[ordered + rest].rename(columns=COL_LABELS)

                    merged    = _reorder(st.session_state["merged_df"])
                    unmatched = _reorder(st.session_state["unmatched_df"])
                    fuzzy_df  = st.session_state["fuzzy_df"]
                    alerts    = (merged[merged["Status"] == "⚠️ Ativo após data de fim"].copy()
                                 if "Status" in merged.columns else merged.iloc[0:0])

                    total     = len(plan_df_x)
                    matched_n = len(merged)
                    pct       = matched_n / total * 100 if total else 0.0

                    m1, m2, m3, m4, m5 = st.columns(5)
                    m1.metric("Total no Plano",      f"{total:,}")
                    m2.metric("Correspondidos",      f"{matched_n:,}", f"{pct:.1f}%")
                    m3.metric("Sem Correspondência", f"{len(unmatched):,}")
                    m4.metric("Sugestões Fuzzy",     f"{len(fuzzy_df):,}")
                    m5.metric("⚠️ Ativos pós-fim",   f"{len(alerts):,}",
                              delta=f"-{len(alerts)}" if len(alerts) else None,
                              delta_color="inverse")

                    t_ok, t_miss, t_alert, t_fuzz = st.tabs([
                        f"✅ Match ({matched_n:,})",
                        f"❌ Sem Match ({len(unmatched):,})",
                        f"⚠️ Alertas ({len(alerts):,})",
                        f"🔍 Fuzzy ({len(fuzzy_df):,})",
                    ])

                    with t_ok:
                        st.dataframe(merged, use_container_width=True, height=420, hide_index=True)
                        _export_buttons(merged, "cruzamento", "exp_merged")

                    with t_miss:
                        if unmatched.empty:
                            st.success("🎉 Todas as linhas do plano foram correspondidas!")
                        else:
                            st.dataframe(unmatched, use_container_width=True, height=420, hide_index=True)
                            _export_buttons(unmatched, "sem_match", "exp_unmatched")

                    with t_alert:
                        if alerts.empty:
                            st.success("Nenhuma peça ativa além da data de fim.")
                        else:
                            st.warning(f"**{len(alerts):,}** registro(s) com impressões/gasto após a data de fim.")
                            ac = [c for c in ["Status","Veículo","Campanha","Grupo de Anúncio",
                                              "Anúncio","Fim Plano","Última Veiculação",
                                              "Impressões","Valor Gasto (R$)"] if c in alerts.columns]
                            st.dataframe(
                                alerts[ac].style.map(
                                    lambda _: "background-color:#3d1f00;color:#ffa657",
                                    subset=["Status"] if "Status" in ac else []),
                                use_container_width=True, height=420, hide_index=True)
                            _export_buttons(alerts[ac], "alertas", "exp_alerts")

                    with t_fuzz:
                        if fuzzy_df.empty:
                            st.success("Nenhuma sugestão fuzzy encontrada.")
                        else:
                            st.caption("Entradas do Plano sem match exato — possíveis erros de digitação:")
                            st.dataframe(
                                fuzzy_df.style.background_gradient(subset=["Score (%)"], cmap="RdYlGn"),
                                use_container_width=True, hide_index=True)

    # ═══════════════════════════════════════════════════════════════════════════
    #  PAGE 2 — DASHBOARD
    # ═══════════════════════════════════════════════════════════════════════════
    elif page == "📊 Dashboard":
        _dh1, _dh2 = st.columns([3, 1])
        with _dh1:
            _page_header("📊", "Dashboard", "Visão consolidada de performance e veiculação")
        d1, d2 = st.columns([3, 1])  # mantém compatibilidade com código abaixo

        all_p_configs = st.session_state.get("all_plan_configs", [])
        all_a_configs = st.session_state.get("all_assets_configs", [])
        p_cfg = st.session_state.get("plan_config", {})
        a_cfg = st.session_state.get("assets_config", {})

        # Construir listas consolidadas para sincronização
        sync_p = all_p_configs if all_p_configs else ([{"veh_id": st.session_state.get("cfg_vehicle_id"), "veh_name": st.session_state.get("cfg_vehicle_name"), "cfg": p_cfg, "mapping": st.session_state.get("plan_mapping",{}), "src_info": st.session_state.get("plan_source","")}] if p_cfg else [])
        sync_a = all_a_configs if all_a_configs else ([{"veh_id": st.session_state.get("cfg_vehicle_id"), "veh_name": st.session_state.get("cfg_vehicle_name"), "cfg": a_cfg, "mapping": st.session_state.get("assets_mapping",{}), "src_info": st.session_state.get("assets_source","")}] if a_cfg else [])

        has_sheets = any((c.get("cfg") or {}).get("src") == "Link (Google Sheets / Office 365)" for c in sync_p + sync_a)

        if has_sheets:
            d2.write("")
            d2.write("")
            if d2.button("🔄 Sincronizar Sheets", use_container_width=True):
                # ── Fase 1: busca dados novos sem salvar (para diff) ──────
                sync_log = st.empty()
                sync_errors: list[str] = []
                _preview_data: dict = {}  # {dtype: {veh_id: {"old": n, "new": n, "df": df, ...}}}

                def _fetch_new(dtype, configs):
                    dtype_label = "Plano" if dtype == "plan" else "Assets"
                    entries = []
                    for idx_s, c_dict in enumerate(configs):
                        veh_id   = c_dict.get("veh_id")
                        veh_name = c_dict.get("veh_name", "Desconhecido")
                        cfg      = c_dict.get("cfg", {})
                        mapping  = c_dict.get("mapping", {})
                        src_info = c_dict.get("src_info", "")
                        c_id     = c_dict.get("camp_id") or st.session_state.get("cfg_campaign_id")
                        if not veh_id:
                            continue
                        sync_log.info(f"🔄 Buscando {dtype_label} · {idx_s+1}/{len(configs)} · **{veh_name}**…")
                        old_df, _, _, _, _ = load_ingestion(c_id, veh_id, dtype)
                        old_n = len(old_df) if old_df is not None else 0

                        if not cfg or cfg.get("src") != "Link (Google Sheets / Office 365)":
                            entries.append({"c_dict": c_dict, "c_id": c_id, "veh_id": veh_id,
                                            "veh_name": veh_name, "df": old_df, "old_n": old_n,
                                            "sheets": False, "dtype": dtype})
                            continue
                        try:
                            df = read_file("url", url=cfg["url"], sheet_name=cfg.get("sheet", 0),
                                           header_row=cfg.get("header_row", 0))
                            if dtype == "plan":
                                veh_col    = cfg.get("veh_col", "(não usar)")
                                veh_filter = cfg.get("veh_filter", "")
                                if veh_col != "(não usar)" and veh_filter.strip():
                                    df = df[df[veh_col].astype(str).str.strip().str.lower() == veh_filter.strip().lower()].copy()
                                if veh_col != "(não usar)" and veh_col in df.columns:
                                    df = df.drop(columns=[veh_col])
                                active = {k: v for k, v in mapping.items() if v != "(não mapear)"}
                                df = normalize_dates(apply_mapping(df, active), ["start_date", "end_date"])
                            else:
                                active = {k: v for k, v in mapping.items() if v != "(não mapear)"}
                                df = apply_mapping(df, active)
                            df["vehicle"] = veh_name
                            if dtype == "plan":
                                df["sys_vehicle"]  = veh_name
                                df["sys_campaign"] = c_dict.get("camp_name", "")
                            entries.append({"c_dict": c_dict, "c_id": c_id, "veh_id": veh_id,
                                            "veh_name": veh_name, "df": df, "old_n": old_n,
                                            "mapping": mapping, "src_info": src_info,
                                            "cfg": cfg, "sheets": True, "dtype": dtype})
                        except Exception as e_veh:
                            sync_errors.append(f"❌ {dtype_label} · **{veh_name}**: {e_veh}")
                    return entries

                try:
                    entries_p = _fetch_new("plan",   sync_p) if sync_p else []
                    entries_a = _fetch_new("assets", sync_a) if sync_a else []
                    sync_log.empty()
                    st.session_state["_sync_preview"] = {
                        "entries_p": entries_p, "entries_a": entries_a, "errors": sync_errors
                    }
                    st.rerun()
                except Exception as e:
                    sync_log.empty()
                    st.error(f"Erro ao buscar dados: {e}")

            # ── Fase 2: mostrar diff e aguardar confirmação ───────────────
            _sp = st.session_state.get("_sync_preview")
            if _sp is not None:
                all_entries = _sp["entries_p"] + _sp["entries_a"]
                sheets_entries = [e for e in all_entries if e.get("sheets")]
                total_old = sum(e["old_n"] for e in sheets_entries)
                total_new = sum(len(e["df"]) if e["df"] is not None else 0 for e in sheets_entries)
                delta = total_new - total_old

                st.info(
                    f"**Prévia da sincronização** · {len(sheets_entries)} veículo(s) com Sheets  \n"
                    f"Antes: **{total_old:,}** linhas → Depois: **{total_new:,}** linhas  "
                    f"(**{delta:+,}**)"
                )
                if _sp["errors"]:
                    for err in _sp["errors"]:
                        st.warning(err)

                with st.expander("Ver detalhes por veículo", expanded=False):
                    for e in sheets_entries:
                        n_new = len(e["df"]) if e["df"] is not None else 0
                        d = n_new - e["old_n"]
                        icon = "🟢" if d >= 0 else "🔴"
                        st.caption(f"{icon} **{e['veh_name']}** ({e['dtype']}) — {e['old_n']:,} → {n_new:,} ({d:+,})")

                sc1, sc2 = st.columns(2)
                if sc1.button("✅ Confirmar e Salvar", type="primary", key="sync_confirm"):
                    _uname = st.session_state.get("username", "")
                    for e in all_entries:
                        df_e = e.get("df")
                        if not e.get("sheets") or df_e is None or df_e.empty:
                            continue
                        try:
                            save_ingestion(e["c_id"], e["veh_id"], e["dtype"], df_e,
                                           e.get("mapping", {}), e.get("src_info", ""),
                                           json.dumps(e.get("cfg", {})), username=_uname)
                        except Exception as exc:
                            st.error(f"Erro ao salvar {e['veh_name']}: {exc}")

                    # Rebuild session df
                    for dtype, entries in [("plan", _sp["entries_p"]), ("assets", _sp["entries_a"])]:
                        all_dfs = [e["df"] for e in entries if e.get("df") is not None and not e["df"].empty]
                        if all_dfs:
                            st.session_state[f"{dtype}_df"] = pd.concat(all_dfs, ignore_index=True)
                            st.session_state[f"all_{dtype}_configs"] = [e["c_dict"] for e in entries]

                    for k in ["merged_df", "unmatched_df", "fuzzy_df", "_cross_sig", "_sync_preview"]:
                        st.session_state.pop(k, None)
                    st.success("Sincronizado com sucesso!")
                    st.rerun()

                if sc2.button("❌ Cancelar", key="sync_cancel"):
                    st.session_state.pop("_sync_preview", None)
                    st.rerun()

        base = st.session_state.get("merged_df")
        if base is None:
            base = st.session_state.get("plan_df")

        if base is None:
            # ── Carregamento automático de TODAS as campanhas ─────────────────
            camps = get_campaigns(username, role)
            if not camps:
                st.warning("Nenhuma campanha disponível para o seu perfil.")
                return

            with st.spinner("Carregando campanhas..."):
                all_plan_dfs = []
                all_assets_dfs = []
                all_plan_configs = []
                all_assets_configs = []

                for camp in camps:
                    camp_id_loop = camp["id"]
                    for v in get_vehicles(camp_id_loop):
                        veh_id   = v["id"]
                        veh_name = v["name"]

                        for dtype, dfs_list, cfgs_list in [
                            ("plan",   all_plan_dfs,   all_plan_configs),
                            ("assets", all_assets_dfs, all_assets_configs),
                        ]:
                            df, mapping, _, src_info, cfg = load_ingestion(camp_id_loop, veh_id, dtype)
                            # Only use rows with actual data — never include empty dfs
                            if df is None or df.empty:
                                continue
                            df = df.copy()
                            df["vehicle"]       = veh_name
                            df["campaign_name"] = camp["name"]
                            # Identity columns stamped pre-merge so they can't be altered by the
                            # fuzzy join — used for filters and Gantt labels (plan only)
                            if dtype == "plan":
                                df["sys_vehicle"]  = veh_name
                                df["sys_campaign"] = camp["name"]
                            dfs_list.append(df)
                            cfgs_list.append({
                                "camp_id":   camp_id_loop,
                                "camp_name": camp["name"],
                                "veh_id":    veh_id,
                                "veh_name":  veh_name,
                                "cfg":       cfg,
                                "mapping":   mapping,
                                "src_info":  src_info,
                            })

                for k in ["merged_df", "unmatched_df", "fuzzy_df", "_cross_sig"]:
                    st.session_state.pop(k, None)

                big_plan   = pd.concat(all_plan_dfs,   ignore_index=True) if all_plan_dfs   else None
                big_assets = pd.concat(all_assets_dfs, ignore_index=True) if all_assets_dfs else None

                if big_plan is not None:
                    st.session_state["plan_df"]          = big_plan
                    st.session_state["all_plan_configs"] = all_plan_configs
                if big_assets is not None:
                    st.session_state["assets_df"]           = big_assets
                    st.session_state["all_assets_configs"]  = all_assets_configs

                if big_plan is not None:
                    available = [c for c in big_plan.columns if c in TAXONOMY_JOIN_FIELDS]
                    if big_assets is not None and "vehicle" in big_plan.columns and "vehicle" in big_assets.columns:
                        available.append("vehicle")
                    if big_assets is not None:
                        assets_agg = aggregate_assets(big_assets, available)
                        matched, unmatched = fuzzy_merge_taxonomy(big_plan, assets_agg, available, threshold=85)
                    else:
                        matched  = big_plan.copy()
                        unmatched = pd.DataFrame()
                    matched = compute_veiculacao_status(matched)
                    st.session_state["merged_df"]    = matched
                    st.session_state["unmatched_df"] = unmatched

                st.session_state["cfg_campaign_id"]   = None
                st.session_state["cfg_campaign_name"] = "Todas as Campanhas"
                st.rerun()

        camp_id = st.session_state.get("cfg_campaign_id")

        if camp_id:
            # single-campaign mode: stamp sys_campaign / sys_client
            camps_meta = get_campaigns(username, role)
            camp_sys_name = ""
            client_name = ""
            for c in camps_meta:
                if c["id"] == camp_id:
                    camp_sys_name = c["name"]
                    client_name = c.get("client_name", "")
                    break
            base["sys_client"]   = client_name
            base["sys_campaign"] = camp_sys_name
        else:
            # all-campaigns mode: derive per-row from campaign_name if sys_campaign absent
            if "sys_campaign" not in base.columns:
                base["sys_campaign"] = base["campaign_name"] if "campaign_name" in base.columns else ""
            if "sys_client" not in base.columns:
                base["sys_client"] = ""

        # ── Filters ───────────────────────────────────────────────────────────
        with st.expander("🔽 Filtros", expanded=True):
            f1, f2, f3, f4, f5 = st.columns(5)

            def _opts(col: str) -> list[str]:
                if col in base.columns:
                    return ["(Todos)"] + sorted(
                        base[col].dropna().astype(str).unique().tolist()
                    )
                return ["(Todos)"]

            _veh_col = "sys_vehicle" if "sys_vehicle" in base.columns else "vehicle"
            sel_client     = f1.selectbox("Cliente", _opts("sys_client"), key="f_cli")
            sel_sys_camp   = f2.selectbox("Campanha (Sistema)", _opts("sys_campaign"), key="f_scamp")
            sel_asset_camp = f3.selectbox("Campanha (Assets)", _opts("campaign_name_asset"), key="f_acamp")
            sel_vehicle    = f4.selectbox("Veículo",  _opts(_veh_col),        key="f_veh")
            sel_vstatus    = f5.selectbox("Status",   _opts("veiculacao_status"), key="f_sts")

            sel_search_dash = st.text_input(
                "🔍 Buscar anúncio / grupo / campanha",
                placeholder="Digite para filtrar por texto…",
                key="f_search_dash",
            )

        filtered = base.copy()
        for col, sel in [
            ("sys_client",          sel_client),
            ("sys_campaign",        sel_sys_camp),
            ("campaign_name_asset", sel_asset_camp),
            (_veh_col,              sel_vehicle),
            ("veiculacao_status",   sel_vstatus),
        ]:
            if sel != "(Todos)" and col in filtered.columns:
                filtered = filtered[filtered[col].astype(str) == sel]

        if sel_search_dash.strip():
            _q = sel_search_dash.strip().lower()
            _text_cols = [c for c in ["ad_name", "ad_group", "campaign_name", "sys_campaign"] if c in filtered.columns]
            if _text_cols:
                _mask = filtered[_text_cols[0]].astype(str).str.lower().str.contains(_q, na=False)
                for _tc in _text_cols[1:]:
                    _mask = _mask | filtered[_tc].astype(str).str.lower().str.contains(_q, na=False)
                filtered = filtered[_mask]

        _active_filters = sum([
            sel_client     != "(Todos)",
            sel_sys_camp   != "(Todos)",
            sel_asset_camp != "(Todos)",
            sel_vehicle    != "(Todos)",
            sel_vstatus    != "(Todos)",
            bool(sel_search_dash.strip()),
        ])
        if _active_filters:
            st.caption(
                f"Exibindo **{len(filtered):,}** de **{len(base):,}** registros  "
                f"·  🔵 **{_active_filters} filtro{'s' if _active_filters > 1 else ''} ativo{'s' if _active_filters > 1 else ''}**"
            )
        else:
            st.caption(f"Exibindo **{len(filtered):,}** de **{len(base):,}** registros")

        # ── Item 13: alertas de campanhas encerrando em ≤7 dias ──────────────
        _today = pd.Timestamp.now().normalize()
        _deadline = _today + pd.Timedelta(days=7)
        _end_col = next((c for c in ["end_date", "data_fim"] if c in filtered.columns), None)
        if _end_col:
            _soon = filtered[
                filtered[_end_col].notna() &
                (pd.to_datetime(filtered[_end_col], errors="coerce") >= _today) &
                (pd.to_datetime(filtered[_end_col], errors="coerce") <= _deadline)
            ]
            if not _soon.empty:
                _camp_col = next((c for c in ["sys_campaign", "campaign_name"] if c in _soon.columns), None)
                _soon_camps = _soon[_camp_col].dropna().unique().tolist() if _camp_col else []
                _label = ", ".join(_soon_camps) if _soon_camps else f"{len(_soon)} registro(s)"
                st.warning(
                    f"⏰ **{len(_soon)} peça(s)** encerram nos próximos 7 dias: {_label}",
                    icon="⏰",
                )

        # ── Item 20: comparação de períodos ──────────────────────────────────
        _date_col = next((c for c in ["start_date", "end_date"] if c in filtered.columns), None)
        if _date_col and not filtered.empty:
            with st.expander("📅 Comparar Períodos", expanded=False):
                _today_dt = pd.Timestamp.now().date()
                _cp1, _cp2 = st.columns(2)
                _pa_s = _cp1.date_input("Período A — início", value=_today_dt - pd.Timedelta(days=60), key="cmp_a_s")
                _pa_e = _cp1.date_input("Período A — fim",    value=_today_dt - pd.Timedelta(days=31), key="cmp_a_e")
                _pb_s = _cp2.date_input("Período B — início", value=_today_dt - pd.Timedelta(days=30), key="cmp_b_s")
                _pb_e = _cp2.date_input("Período B — fim",    value=_today_dt,                         key="cmp_b_e")

                _num_cols = [c for c in ["impressions","clicks","views","spend"] if c in filtered.columns]

                if _num_cols and st.button("🔀 Comparar", type="primary", key="cmp_run"):
                    def _period_filter(df, start, end, col):
                        _s = pd.to_datetime(df[col], errors="coerce")
                        return df[(_s.dt.date >= start) & (_s.dt.date <= end)]

                    _fa = _period_filter(filtered, _pa_s, _pa_e, _date_col)
                    _fb = _period_filter(filtered, _pb_s, _pb_e, _date_col)

                    def _to_num_col(df, col):
                        return pd.to_numeric(
                            df[col].astype(str).str.replace(r"[^\d.,]","",regex=True)
                                   .str.replace(".","",regex=False).str.replace(",",".",regex=False),
                            errors="coerce"
                        ).fillna(0)

                    _rows = []
                    for _nc in _num_cols:
                        _va = _to_num_col(_fa, _nc).sum() if not _fa.empty else 0
                        _vb = _to_num_col(_fb, _nc).sum() if not _fb.empty else 0
                        _delta = _vb - _va
                        _pct   = (_delta / _va * 100) if _va else None
                        _rows.append({
                            "Métrica":          FIELD_LABELS.get(_nc, _nc),
                            f"A ({_pa_s}→{_pa_e})": f"{_va:,.0f}",
                            f"B ({_pb_s}→{_pb_e})": f"{_vb:,.0f}",
                            "Variação":         f"{_delta:+,.0f}",
                            "Variação %":       f"{_pct:+.1f}%" if _pct is not None else "—",
                        })
                    st.dataframe(pd.DataFrame(_rows), use_container_width=True, hide_index=True)
                    st.caption(f"Período A: **{len(_fa):,}** linhas · Período B: **{len(_fb):,}** linhas")

        if filtered.empty:
            st.warning("Nenhum dado disponível para exibir no Dashboard. Se você acabou de criar a campanha, acesse 'Mapeamento & Cruzamento' para ingerir os dados.")
        else:
            # ── Gantt ─────────────────────────────────────────────────────────────
            try:
                gantt_chart(filtered)
            except Exception as e:
                st.warning(f"Gantt indisponível: {e}")

            # ── Summary charts ────────────────────────────────────────────────────
            _BG = dict(paper_bgcolor="#0d1117", font_color="#c9d1d9", plot_bgcolor="#0d1117")
    
            _dash_veh_col = "sys_vehicle" if "sys_vehicle" in filtered.columns else "vehicle"
            has_status  = "veiculacao_status" in filtered.columns
            has_vehicle = _dash_veh_col in filtered.columns

            if has_status or has_vehicle:
                cc1, cc2 = st.columns(2)

                if has_status:
                    with cc1:
                        vc = filtered["veiculacao_status"].value_counts().reset_index()
                        vc.columns = ["Status", "Qtd"]
                        fig = px.pie(
                            vc, names="Status", values="Qtd",
                            title="Distribuição por Status",
                            color_discrete_sequence=px.colors.qualitative.Dark24,
                        )
                        fig.update_layout(**_BG)
                        st.plotly_chart(fig, use_container_width=True)

                if has_vehicle:
                    with cc2:
                        vc = filtered[_dash_veh_col].value_counts().reset_index()
                        vc.columns = ["Veículo", "Qtd"]
                        fig = px.bar(
                            vc, x="Veículo", y="Qtd", color="Veículo",
                            title="Peças por Veículo / Canal",
                            color_discrete_sequence=px.colors.qualitative.Dark24,
                        )
                        fig.update_layout(
                            **_BG, showlegend=False,
                            xaxis=dict(gridcolor="#21262d"),
                            yaxis=dict(gridcolor="#21262d"),
                        )
                        st.plotly_chart(fig, use_container_width=True)
    
            if "format" in filtered.columns:
                vc = filtered["format"].value_counts().reset_index()
                vc.columns = ["Formato", "Qtd"]
                fig = px.bar(
                    vc, x="Formato", y="Qtd", color="Formato",
                    title="Peças por Formato",
                    color_discrete_sequence=px.colors.qualitative.Dark24,
                )
                fig.update_layout(
                    **_BG, showlegend=False,
                    xaxis=dict(gridcolor="#21262d"),
                    yaxis=dict(gridcolor="#21262d"),
                )
                st.plotly_chart(fig, use_container_width=True)

        # ── Item 17: orçamento vs gasto ──────────────────────────────────────
        if "budget" in filtered.columns and "spend" in filtered.columns:
            def _to_num(s):
                try:
                    if pd.isna(s): return 0.0
                    return float(str(s).replace("R$","").replace(".","").replace(",",".").strip())
                except Exception: return 0.0

            _bv = filtered.copy()
            _bv["_budget_n"] = _bv["budget"].apply(_to_num)
            _bv["_spend_n"]  = _bv["spend"].apply(_to_num)
            _grp_col = "sys_vehicle" if "sys_vehicle" in _bv.columns else (
                        "sys_campaign" if "sys_campaign" in _bv.columns else None)
            if _grp_col and (_bv["_budget_n"].sum() > 0 or _bv["_spend_n"].sum() > 0):
                st.divider()
                st.subheader("💰 Orçamento vs Gasto")
                _agg = (_bv.groupby(_grp_col)
                          .agg(Orçamento=("_budget_n","sum"), Gasto=("_spend_n","sum"))
                          .reset_index()
                          .rename(columns={_grp_col: "Veículo/Campanha"}))
                _agg["% Utilizado"] = (_agg["Gasto"] / _agg["Orçamento"].replace(0, float("nan")) * 100).round(1)

                _bm1, _bm2, _bm3 = st.columns(3)
                _tot_bud = _agg["Orçamento"].sum()
                _tot_spd = _agg["Gasto"].sum()
                _tot_pct = (_tot_spd / _tot_bud * 100) if _tot_bud else 0
                _bm1.metric("Orçamento Total", f"R$ {_tot_bud:,.0f}".replace(",","X").replace(".",",").replace("X","."))
                _bm2.metric("Gasto Total",     f"R$ {_tot_spd:,.0f}".replace(",","X").replace(".",",").replace("X","."))
                _bm3.metric("% Utilizado", f"{_tot_pct:.1f}%",
                            delta=f"{'acima' if _tot_pct>100 else 'dentro'} do orçamento",
                            delta_color="inverse" if _tot_pct>100 else "normal")

                _fig_bud = px.bar(
                    _agg.melt(id_vars="Veículo/Campanha", value_vars=["Orçamento","Gasto"],
                              var_name="Tipo", value_name="Valor (R$)"),
                    x="Veículo/Campanha", y="Valor (R$)", color="Tipo", barmode="group",
                    title="Orçamento vs Gasto por Veículo/Campanha",
                    color_discrete_map={"Orçamento": "#58a6ff", "Gasto": "#3fb950"},
                )
                _fig_bud.update_layout(
                    **dict(paper_bgcolor="#0d1117", font_color="#c9d1d9", plot_bgcolor="#0d1117"),
                    xaxis=dict(gridcolor="#21262d"), yaxis=dict(gridcolor="#21262d"),
                )
                st.plotly_chart(_fig_bud, use_container_width=True)
                st.dataframe(_agg, use_container_width=True, hide_index=True)

        # ── Tabela de criativos ───────────────────────────────────────────────
        st.divider()
        
        c_src1, c_src2 = st.columns(2)
        p_src = st.session_state.get("plan_source")
        a_src = st.session_state.get("assets_source")
        
        def render_source(label: str, src: str):
            if not src:
                return f"**{label}:** (Não cadastrado)"
            if src.startswith("Link: "):
                url = src.replace("Link: ", "").strip()
                return f"**{label}:** [Acessar Planilha]({url})"
            return f"**{label}:** {src}"

        c_src1.info(render_source("Origem do Plano", p_src))
        c_src2.info(render_source("Origem dos Assets", a_src))

        st.subheader("📋 Criativos")

        TABLE_COLS = {
            "veiculacao_status": "Status",
            "_quality":          "Qualidade Match",
            "vehicle":           "Veículo",
            "campaign_name":     "Campanha",
            "ad_group":          "Grupo de Anúncio",
            "ad_name":           "Anúncio",
            "start_date":        "Início Plano",
            "end_date":          "Fim Plano",
            "date":              "Última Veiculação",
            "impressions":       "Impressões",
            "clicks":            "Cliques",
            "views":             "Views",
            "spend":             "Valor Gasto (R$)",
        }
        # Adiciona coluna de qualidade baseada em _match_type
        if "_match_type" in filtered.columns:
            def _quality_badge(v):
                if pd.isna(v) or not v:
                    return "❌ Sem match"
                s = str(v).lower()
                if s == "exato":
                    return "✅ Exato"
                if s.startswith("fuzzy"):
                    return f"🟡 {v}"
                return str(v)
            filtered = filtered.copy()
            filtered["_quality"] = filtered["_match_type"].apply(_quality_badge)

        ordered = [c for c in TABLE_COLS if c in filtered.columns]
        rest    = [c for c in filtered.columns if c not in ordered and not c.startswith("_")]
        tbl = filtered[ordered + rest].rename(columns=TABLE_COLS)

        st.dataframe(tbl, use_container_width=True, hide_index=True, height=420)
        _export_buttons(tbl, "criativos", "exp_dash_tbl")


    # ═══════════════════════════════════════════════════════════════════════════
    #  PAGE — CAMPANHAS EM VEICULAÇÃO
    # ═══════════════════════════════════════════════════════════════════════════
    elif page == "📡 Campanhas em Veiculação":
        _page_header("📡", "Campanhas em Veiculação", "Acompanhe status, datas e cobertura das campanhas ativas")

        # Página acessível a todos os perfis (config da planilha somente admin)

        # ── Configuração da planilha (somente admin) ─────────────────────────
        saved_cfg = load_campaign_sheets_config()

        if role == "admin":
          with st.expander("⚙️ Configuração da Planilha Google Sheets", expanded=saved_cfg is None):
            cfg_url = st.text_input(
                "Link da Planilha (Google Sheets)",
                value=saved_cfg["sheet_url"] if saved_cfg else "",
                placeholder="https://docs.google.com/spreadsheets/d/.../edit",
                key="camp_sheet_url",
            )

            if cfg_url:
                # Detect sheets
                cache_key = f"_camp_sheets_{cfg_url}"
                if st.session_state.get("_camp_sheets_url_last") != cfg_url:
                    with st.spinner("Detectando abas..."):
                        st.session_state[cache_key] = get_sheets_from_url(cfg_url)
                    st.session_state["_camp_sheets_url_last"] = cfg_url

                sheet_list = st.session_state.get(cache_key, [])
                cfg_sheet = (
                    st.selectbox(
                        "Aba (Sheet)", sheet_list,
                        index=sheet_list.index(saved_cfg["sheet_name"]) if saved_cfg and saved_cfg["sheet_name"] in sheet_list else 0,
                        key="camp_sheet_name",
                    ) if len(sheet_list) > 1 else (sheet_list[0] if sheet_list else "")
                )

                cfg_header = st.number_input(
                    "Linha do cabeçalho", 1, 100,
                    value=saved_cfg["header_row"] if saved_cfg else 1,
                    key="camp_sheet_hrow",
                    help="Número da linha onde ficam os nomes das colunas na planilha (normalmente 1).",
                )

                # Preview columns to map
                preview_fp = (cfg_url, str(cfg_sheet), str(cfg_header))
                if st.session_state.get("_camp_preview_fp") != preview_fp:
                    with st.spinner("Carregando prévia da planilha..."):
                        try:
                            st.session_state["_camp_preview_df"] = read_file(
                                "url", url=cfg_url,
                                sheet_name=cfg_sheet if cfg_sheet else 0,
                                header_row=int(cfg_header) - 1,
                            )
                            st.session_state["_camp_preview_fp"] = preview_fp
                        except Exception as e:
                            st.error(f"Erro ao carregar prévia: {e}")

                preview_df = st.session_state.get("_camp_preview_df")
                if preview_df is not None:
                    st.success(f"✅ {len(preview_df):,} linhas · {len(preview_df.columns)} colunas detectadas")
                    with st.expander("Prévia dos dados brutos", expanded=False):
                        st.dataframe(preview_df.head(5), use_container_width=True)

                    cols_opt = ["(não mapear)"] + list(preview_df.columns)

                    st.markdown("##### Mapeamento de Colunas")
                    mc1, mc2 = st.columns(2)

                    def _guess(keyword: str) -> int:
                        kw = keyword.lower().replace(" ", "").replace("_", "")
                        for i, c in enumerate(cols_opt):
                            if kw in str(c).lower().replace(" ", "").replace("_", ""):
                                return i
                        return 0

                    with mc1:
                        sel_cliente = st.selectbox(
                            "Cliente", cols_opt,
                            index=cols_opt.index(saved_cfg.get("col_cliente", "")) if saved_cfg and saved_cfg.get("col_cliente", "") in cols_opt else _guess("cliente"),
                            key="camp_col_cliente",
                        )
                        sel_campanha = st.selectbox(
                            "Nome da Campanha", cols_opt,
                            index=cols_opt.index(saved_cfg.get("col_campanha", "")) if saved_cfg and saved_cfg.get("col_campanha", "") in cols_opt else _guess("campanha"),
                            key="camp_col_campanha",
                        )
                        sel_veiculos = st.selectbox(
                            "Veículos", cols_opt,
                            index=cols_opt.index(saved_cfg.get("col_veiculos", "")) if saved_cfg and saved_cfg.get("col_veiculos", "") in cols_opt else _guess("veiculo"),
                            key="camp_col_veiculos",
                        )
                    with mc2:
                        sel_inicio = st.selectbox(
                            "Data de Início", cols_opt,
                            index=cols_opt.index(saved_cfg.get("col_inicio", "")) if saved_cfg and saved_cfg.get("col_inicio", "") in cols_opt else _guess("inicio"),
                            key="camp_col_inicio",
                        )
                        sel_fim = st.selectbox(
                            "Data Final", cols_opt,
                            index=cols_opt.index(saved_cfg.get("col_fim", "")) if saved_cfg and saved_cfg.get("col_fim", "") in cols_opt else _guess("fim"),
                            key="camp_col_fim",
                        )
                        sel_link_plano = st.selectbox(
                            "Link Plano de Conteúdo", cols_opt,
                            index=cols_opt.index(saved_cfg.get("col_link_plano", "")) if saved_cfg and saved_cfg.get("col_link_plano", "") in cols_opt else _guess("plano"),
                            key="camp_col_plano",
                        )
                        sel_link_dash = st.selectbox(
                            "Link Dashboard Agência", cols_opt,
                            index=cols_opt.index(saved_cfg.get("col_link_dash", "")) if saved_cfg and saved_cfg.get("col_link_dash", "") in cols_opt else _guess("dash"),
                            key="camp_col_dash",
                        )

                    if st.button("💾 Salvar configuração", type="primary", key="camp_save_cfg"):
                        _sel = lambda v: v if v != "(não mapear)" else ""
                        save_campaign_sheets_config(
                            sheet_url=cfg_url,
                            sheet_name=cfg_sheet if cfg_sheet else "",
                            col_cliente=_sel(sel_cliente),
                            col_campanha=_sel(sel_campanha),
                            col_inicio=_sel(sel_inicio),
                            col_fim=_sel(sel_fim),
                            col_veiculos=_sel(sel_veiculos),
                            col_link_plano=_sel(sel_link_plano),
                            col_link_dash=_sel(sel_link_dash),
                            header_row=int(cfg_header),
                        )
                        # Clear cached data to force reload
                        st.session_state.pop("_camp_data", None)
                        st.success("Configuração salva! Recarregando dados...")
                        st.rerun()

        # ── Load campaign data ────────────────────────────────────────────────
        cfg = load_campaign_sheets_config()
        if not cfg:
            st.info("📋 A planilha do Google Sheets ainda não foi configurada. Solicite a um administrador.")
            st.divider()
            st.subheader("📢 Campanhas cadastradas no sistema")
            st.caption("Exibindo campanhas registradas no módulo de Mapeamento enquanto a planilha não é configurada.")
            _fb_camps = get_campaigns(username=username, role=role)
            if not _fb_camps:
                st.warning("Nenhuma campanha cadastrada ainda.")
            else:
                for _fc in _fb_camps:
                    _fvehs = get_vehicles(_fc["id"])
                    _vnames = ", ".join(v["name"] for v in _fvehs) if _fvehs else "—"
                    _cli = _fc.get("client_name") or "—"
                    st.markdown(
                        f"**{_fc['name']}** · 👤 {_cli} · 📺 {_vnames}"
                    )
                    st.markdown("---")
            return

        # Sync button
        sc1, sc2 = st.columns([5, 1])
        sc2.write("")
        if sc2.button("🔄 Atualizar", use_container_width=True, key="camp_sync"):
            st.session_state.pop("_camp_data", None)

        if "_camp_data" not in st.session_state:
            with st.spinner("Carregando campanhas do Google Sheets..."):
                try:
                    camp_df = read_campaign_sheet(
                        sheet_url=cfg["sheet_url"],
                        sheet_name=cfg["sheet_name"] if cfg["sheet_name"] else 0,
                        header_row=int(cfg["header_row"]) - 1,
                        col_cliente=cfg["col_cliente"],
                        col_campanha=cfg["col_campanha"],
                        col_inicio=cfg["col_inicio"],
                        col_fim=cfg["col_fim"],
                        col_veiculos=cfg["col_veiculos"],
                        col_link_plano=cfg["col_link_plano"],
                        col_link_dash=cfg["col_link_dash"],
                    )
                    st.session_state["_camp_data"] = camp_df
                except Exception as e:
                    st.error(f"Erro ao carregar dados: {e}")
                    return

        camp_df = st.session_state.get("_camp_data")
        if camp_df is None or camp_df.empty:
            st.warning("Nenhuma campanha encontrada na planilha.")
            return

        # ── Verificação: veículos cadastrados no Mapeamento ───────────────
        db_campaigns = get_campaigns(role="admin")
        db_camp_map = {}  # {campaign_name_lower: campaign_id}
        for c in db_campaigns:
            db_camp_map[c["name"].strip().lower()] = c["id"]

        # Build set of registered (campaign, vehicle) pairs
        registered_pairs = set()
        for c in db_campaigns:
            vehs = get_vehicles(c["id"])
            for v in vehs:
                registered_pairs.add((c["name"].strip().lower(), v["name"].strip().lower()))

        # Check each row from the sheet
        missing = []
        active_df = camp_df[camp_df["status_campanha"].isin(["🟢 Em veiculação", "📅 Aguardando início"])]
        checked = set()
        for _, row in active_df.iterrows():
            campanha = str(row["campanha"]).strip()
            veiculo = str(row["veiculos"]).strip()
            if not campanha or not veiculo:
                continue
            pair_key = (campanha.lower(), veiculo.lower())
            if pair_key in checked:
                continue
            checked.add(pair_key)

            camp_found = campanha.lower() in db_camp_map
            veh_found = pair_key in registered_pairs

            if not camp_found:
                missing.append({
                    "cliente": row.get("cliente", ""),
                    "campanha": campanha,
                    "veiculo": veiculo,
                    "problema": "❌ Campanha não cadastrada",
                })
            elif not veh_found:
                missing.append({
                    "cliente": row.get("cliente", ""),
                    "campanha": campanha,
                    "veiculo": veiculo,
                    "problema": "⚠️ Veículo não cadastrado",
                })

        if missing:
            with st.expander(f"🚨 **{len(missing)} veículo(s) pendentes no Mapeamento** — clique para ver", expanded=True):
                st.markdown(
                    "<p style='color:#f0883e;font-size:0.9em'>"
                    "Os veículos abaixo constam no controle de campanhas mas ainda não foram cadastrados "
                    "no módulo de <b>Mapeamento & Cruzamento</b>.</p>",
                    unsafe_allow_html=True,
                )

                # Agrupa por campanha para detectar múltiplos veículos
                _miss_by_camp: dict[str, list[dict]] = {}
                for _m in missing:
                    _miss_by_camp.setdefault(_m["campanha"], []).append(_m)

                for _camp_name, _camp_missing in _miss_by_camp.items():
                    _camp_client = _camp_missing[0].get("cliente", "")
                    _vehs_missing = [_m["veiculo"] for _m in _camp_missing]
                    _problema = _camp_missing[0]["problema"]
                    _is_multi = len(_vehs_missing) > 1

                    _mc1, _mc2 = st.columns([5, 2])
                    with _mc1:
                        st.markdown(
                            f"**{_camp_name}**  ·  `{_camp_client}`  ·  "
                            f"<span style='color:#f0883e'>{_problema}</span>  ·  "
                            f"{len(_vehs_missing)} veículo(s): {', '.join(_vehs_missing)}",
                            unsafe_allow_html=True,
                        )

                    with _mc2:
                        if _is_multi and role in ["admin", "editor"]:
                            # Lote: cria campanha + todos os veículos de uma vez
                            if st.button(
                                f"📥 Criar em lote ({len(_vehs_missing)} veículos)",
                                key=f"miss_batch_{_camp_name}",
                                type="primary",
                            ):
                                try:
                                    _existing_camps = {c["name"].lower(): c["id"] for c in get_campaigns(role="admin", include_archived=True)}
                                    if _camp_name.lower() in _existing_camps:
                                        _new_cid = _existing_camps[_camp_name.lower()]
                                    else:
                                        _new_cid = create_campaign(_camp_name, _camp_client)
                                    _veh_ok, _veh_skip = 0, 0
                                    for _vn in _vehs_missing:
                                        try:
                                            create_vehicle(_new_cid, _vn)
                                            _veh_ok += 1
                                        except Exception:
                                            _veh_skip += 1
                                    log_audit(username, "criar_em_lote", "campanha", _camp_name,
                                              f"{_veh_ok} veículo(s) criados via pendentes")
                                    st.success(f"✅ {_camp_name}: {_veh_ok} veículo(s) criado(s).")
                                    st.rerun()
                                except Exception as _be:
                                    st.error(str(_be))
                        elif role in ["admin", "editor"]:
                            # Individual: navega para o mapeamento com a campanha pré-selecionada
                            if st.button(
                                "➕ Cadastrar",
                                key=f"miss_create_{_camp_name}",
                                type="primary",
                            ):
                                try:
                                    _existing_camps = {c["name"].lower(): c["id"] for c in get_campaigns(role="admin", include_archived=True)}
                                    if _camp_name.lower() in _existing_camps:
                                        _new_cid = _existing_camps[_camp_name.lower()]
                                    else:
                                        _new_cid = create_campaign(_camp_name, _camp_client)
                                    for _vn in _vehs_missing:
                                        try:
                                            create_vehicle(_new_cid, _vn)
                                        except Exception:
                                            pass
                                    log_audit(username, "criar", "campanha", _camp_name,
                                              f"Criado via pendentes: {', '.join(_vehs_missing)}")
                                    # Navega direto para o mapeamento com essa campanha
                                    st.session_state["page"] = "📥 Mapeamento & Cruzamento"
                                    st.session_state["cfg_campaign_id"]   = _new_cid
                                    st.session_state["cfg_campaign_name"] = _camp_name
                                    st.rerun()
                                except Exception as _ce:
                                    st.error(str(_ce))

                    st.divider()

        # ── KPI Cards (conta campanhas únicas) ────────────────────────────────
        unique_camps = camp_df.drop_duplicates(subset=["cliente", "campanha"])
        total_c = len(unique_camps)
        em_veiculacao_c = len(unique_camps[unique_camps["status_campanha"] == "🟢 Em veiculação"])
        aguardando_c = len(unique_camps[unique_camps["status_campanha"] == "📅 Aguardando início"])
        finalizadas_c = len(unique_camps[unique_camps["status_campanha"] == "🏁 Finalizada"])
        sem_datas_c = len(unique_camps[unique_camps["status_campanha"] == "⏳ Sem datas"])

        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric("Campanhas", f"{total_c}")
        k2.metric("🟢 Em Veiculação", f"{em_veiculacao_c}")
        k3.metric("📅 Aguardando", f"{aguardando_c}")
        k4.metric("🏁 Finalizadas", f"{finalizadas_c}")
        k5.metric("⏳ Sem Datas", f"{sem_datas_c}")

        st.divider()

        # ── Filters ───────────────────────────────────────────────────────────
        with st.expander("🔽 Filtros", expanded=True):
            ff1, ff2, ff3 = st.columns(3)

            clientes = sorted(camp_df["cliente"].unique().tolist())
            statuses = sorted(camp_df["status_campanha"].unique().tolist())

            sel_cli_f = ff1.selectbox("Cliente", ["(Todos)"] + clientes, key="camp_f_cli")
            sts_opts = ["(Todos)"] + statuses
            default_sts = sts_opts.index("🟢 Em veiculação") if "🟢 Em veiculação" in sts_opts else 0
            sel_sts_f = ff2.selectbox("Status", sts_opts, index=default_sts, key="camp_f_sts")
            sel_search = ff3.text_input("🔍 Buscar campanha", key="camp_f_search")

        filtered = camp_df.copy()
        if sel_cli_f != "(Todos)":
            filtered = filtered[filtered["cliente"] == sel_cli_f]
        if sel_sts_f != "(Todos)":
            filtered = filtered[filtered["status_campanha"] == sel_sts_f]
        if sel_search.strip():
            mask = filtered["campanha"].str.lower().str.contains(sel_search.strip().lower(), na=False)
            filtered = filtered[mask]

        st.caption(f"Exibindo **{len(filtered):,}** linhas · **{filtered.drop_duplicates(subset=['cliente','campanha']).shape[0]}** campanhas únicas")

        # ── Gantt-style timeline (cada veículo = 1 linha, agrupado por campanha)
        plot_df = filtered.dropna(subset=["data_inicio", "data_fim"]).copy()
        if not plot_df.empty:
            plot_df["row_label"] = plot_df["campanha"].str.strip() + "  ·  " + plot_df["veiculos"].str.strip()
            plot_df = plot_df.sort_values(["cliente", "campanha", "veiculos"]).reset_index(drop=True)
            row_labels_ordered = plot_df["row_label"].unique().tolist()

            fig = px.timeline(
                plot_df,
                x_start="data_inicio",
                x_end="data_fim",
                y="row_label",
                color="veiculos",
                text="veiculos",
                hover_data={"cliente": True, "campanha": True, "veiculos": True,
                            "status_campanha": True, "dias_restantes": True},
                color_discrete_sequence=px.colors.qualitative.Dark24,
            )
            fig.update_yaxes(
                autorange="reversed", title="",
                categoryorder="array", categoryarray=row_labels_ordered,
                tickfont=dict(size=12, color="#c9d1d9"),
            )
            fig.update_xaxes(title="", tickfont=dict(size=12))
            fig.update_traces(
                textposition="inside", insidetextanchor="middle",
                textfont=dict(size=12, color="#ffffff"),
            )

            # Separadores entre campanhas diferentes
            camps_list = [plot_df[plot_df["row_label"] == lbl].iloc[0]["campanha"] for lbl in row_labels_ordered]
            for i in range(1, len(camps_list)):
                if camps_list[i] != camps_list[i - 1]:
                    fig.add_shape(
                        type="line", x0=0, x1=1, xref="paper",
                        y0=i - 0.5, y1=i - 0.5,
                        line=dict(color="#30363d", width=1),
                    )

            # Linha "Hoje"
            today_dt = pd.Timestamp.now().normalize().to_pydatetime()
            fig.add_shape(type="line", x0=today_dt, x1=today_dt, y0=0, y1=1,
                          yref="paper", line=dict(dash="dash", color="#f97583", width=2))
            fig.add_annotation(x=today_dt, y=1.02, yref="paper", text="Hoje",
                               showarrow=False, font=dict(color="#f97583", size=12))

            n_rows = len(row_labels_ordered)
            chart_height = max(350, n_rows * 40 + 120)
            max_visible = 600
            fig.update_layout(
                plot_bgcolor="#0d1117",
                paper_bgcolor="#0d1117",
                font=dict(color="#c9d1d9", size=12),
                title=dict(text="📅 Timeline de Campanhas", font=dict(size=15)),
                height=chart_height,
                legend_title="Veículo",
                legend=dict(font=dict(size=11)),
                xaxis=dict(showgrid=True, gridcolor="#21262d", side="top"),
                yaxis=dict(showgrid=False),
                margin=dict(l=10, r=10, t=80, b=10),
            )
            if chart_height > max_visible:
                with st.container(height=max_visible):
                    st.plotly_chart(fig, use_container_width=True)
            else:
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Nenhuma campanha com datas válidas para exibir no Gantt.")

        # ── Summary charts ────────────────────────────────────────────────────
        if not filtered.empty:
            _BG2 = dict(paper_bgcolor="#0d1117", font_color="#c9d1d9", plot_bgcolor="#0d1117")
    
            ch1, ch2 = st.columns(2)
            with ch1:
                vc = filtered["status_campanha"].value_counts().reset_index()
                vc.columns = ["Status", "Qtd"]
                fig = px.pie(
                    vc, names="Status", values="Qtd",
                    title="Distribuição por Status",
                    color="Status",
                    color_discrete_map={
                        "🟢 Em veiculação": "#3fb950",
                        "📅 Aguardando início": "#58a6ff",
                        "🏁 Finalizada": "#8b949e",
                        "⏳ Sem datas": "#f0883e",
                    },
                )
                fig.update_layout(**_BG2)
                st.plotly_chart(fig, use_container_width=True)
    
            with ch2:
                cli_counts = filtered["cliente"].value_counts().reset_index()
                cli_counts.columns = ["Cliente", "Campanhas"]
                fig = px.bar(
                    cli_counts, x="Cliente", y="Campanhas", color="Cliente",
                    title="Campanhas por Cliente",
                    color_discrete_sequence=px.colors.qualitative.Dark24,
                )
                fig.update_layout(
                    **_BG2, showlegend=False,
                    xaxis=dict(gridcolor="#21262d"),
                    yaxis=dict(gridcolor="#21262d"),
                )
                st.plotly_chart(fig, use_container_width=True)

        # ── Campaign cards (agrupados por campanha) ───────────────────────────
        st.divider()
        st.subheader("📋 Detalhes das Campanhas")

        STATUS_COLORS = {
            "🟢 Em veiculação":     ("#0f291b", "#3fb950"),
            "📅 Aguardando início": ("#0d1d30", "#58a6ff"),
            "🏁 Finalizada":        ("#161b22", "#8b949e"),
            "⏳ Sem datas":         ("#2a1d0f", "#f0883e"),
        }

        grouped = filtered.groupby(["cliente", "campanha"], sort=False)
        for (cliente, campanha), grp in grouped:
            first = grp.iloc[0]
            status = first["status_campanha"]
            bg_color, accent = STATUS_COLORS.get(status, ("#161b22", "#8b949e"))
            dias = first["dias_restantes"]

            if pd.notna(dias):
                dias_int = int(dias)
                if dias_int > 0:
                    dias_label = f"{dias_int} dia(s) restante(s)" if status == "🟢 Em veiculação" else f"Inicia em {dias_int} dia(s)"
                elif dias_int < 0:
                    dias_label = f"Finalizada há {abs(dias_int)} dia(s)"
                else:
                    dias_label = "Último dia!"
            else:
                dias_label = ""

            ini_str = first["data_inicio"].strftime("%d/%m/%Y") if pd.notna(first["data_inicio"]) else "—"
            fim_str = first["data_fim"].strftime("%d/%m/%Y") if pd.notna(first["data_fim"]) else "—"
            veiculos_list = grp["veiculos"].dropna().unique().tolist()
            veiculos_str = ", ".join(v for v in veiculos_list if v) or "—"

            veh_badges = "".join(
                f'<span style="display:inline-block;background:#21262d;border-radius:4px;padding:2px 8px;margin:2px 4px 2px 0;font-size:0.8em;color:#c9d1d9">{v}</span>'
                for v in veiculos_list if v
            ) or '<span style="color:#484f58">—</span>'

            # Pre-build links to avoid f-string complexity inside markdown
            plano_link = ""
            if pd.notna(first.get("link_plano")) and str(first["link_plano"]).startswith("http"):
                plano_link = f'<a href="{first["link_plano"]}" target="_blank" style="text-decoration:none;color:#58a6ff;font-size:0.85em;display:flex;align-items:center;gap:4px">📋 Plano</a>'
            
            dash_link = ""
            if pd.notna(first.get("link_dash")) and str(first["link_dash"]).startswith("http"):
                dash_link = f'<a href="{first["link_dash"]}" target="_blank" style="text-decoration:none;color:#58a6ff;font-size:0.85em;display:flex;align-items:center;gap:4px">📊 Dash</a>'

            # Build card HTML as a single continuous string to avoid markdown interjection
            card_html = (
                f'<div style="background:{bg_color}; border-left:4px solid {accent}; border-radius:8px; padding:16px 20px; margin-bottom:10px;">'
                f'<div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">'
                f'<div><span style="font-size:1.1em; font-weight:700; color:#e6edf3">{campanha}</span>'
                f'<span style="color:{accent}; margin-left:12px; font-size:0.85em">{status}</span></div>'
                f'<span style="color:#8b949e; font-size:0.8em">{dias_label}</span></div>'
                f'<div style="margin-top:8px; display:flex; gap:24px; flex-wrap:wrap; color:#8b949e; font-size:0.85em;">'
                f'<span>👤 <b>{cliente or "—"}</b></span><span>📅 {ini_str} → {fim_str}</span></div>'
                f'<div style="margin-top:6px; display:flex; justify-content:space-between; align-items:center;">'
                f'<div>📺 {veh_badges}</div><div style="display:flex; gap:12px;">{plano_link}{dash_link}</div></div></div>'
            )
            st.markdown(card_html, unsafe_allow_html=True)

        # ── Item 36: Calendário mensal ────────────────────────────────────────
        st.divider()
        st.subheader("📅 Calendário de Campanhas")

        _cal_today = pd.Timestamp.now().normalize()
        _cal_col1, _cal_col2 = st.columns([1, 4])
        _cal_month_offset = _cal_col1.number_input(
            "Mês (0 = atual)", min_value=-12, max_value=12, value=0,
            step=1, key="cal_month_offset",
        )
        _cal_ref = (_cal_today + pd.DateOffset(months=int(_cal_month_offset))).replace(day=1)
        _cal_year, _cal_month = _cal_ref.year, _cal_ref.month
        import calendar as _calendar_mod
        _cal_days_in_month = _calendar_mod.monthrange(_cal_year, _cal_month)[1]
        _cal_col2.caption(
            f"**{_cal_ref.strftime('%B %Y').capitalize()}** · {_cal_days_in_month} dias"
        )

        # Build calendar HTML
        _cal_camps_cal = filtered[filtered["data_inicio"].notna() | filtered["data_fim"].notna()].copy()
        _STATUS_COLORS = {
            "🟢 Em veiculação": "#238636",
            "📅 Aguardando":    "#1f6feb",
            "🏁 Finalizada":    "#6e7681",
            "⏳ Sem datas":     "#30363d",
        }

        _cal_day_cols = [str(d) for d in range(1, _cal_days_in_month + 1)]
        _cal_rows_html = ""
        for _, _cr in _cal_camps_cal.iterrows():
            _c_start = _cr.get("data_inicio")
            _c_end   = _cr.get("data_fim")
            _c_name  = str(_cr.get("campanha", ""))[:30]
            _c_status = str(_cr.get("status_campanha", ""))
            _c_color  = _STATUS_COLORS.get(_c_status, "#30363d")
            _cells = ""
            for _d in range(1, _cal_days_in_month + 1):
                _day_ts = pd.Timestamp(_cal_year, _cal_month, _d)
                _in_range = True
                if pd.notna(_c_start) and _day_ts < pd.Timestamp(_c_start): _in_range = False
                if pd.notna(_c_end)   and _day_ts > pd.Timestamp(_c_end):   _in_range = False
                _is_today = _day_ts.date() == _cal_today.date()
                _bg = _c_color if _in_range else "transparent"
                _border = "2px solid #f0883e" if _is_today else "1px solid transparent"
                _cells += f'<td style="background:{_bg};border:{_border};width:18px;height:18px;border-radius:3px"></td>'
            _cal_rows_html += f"""
            <tr>
              <td style="color:#cdd9e5;font-size:11px;padding-right:8px;white-space:nowrap;max-width:180px;overflow:hidden;text-overflow:ellipsis">{_c_name}</td>
              {_cells}
            </tr>"""

        _header_cells = "".join(
            f'<th style="color:#8b949e;font-size:10px;width:18px;text-align:center">'
            f'{"<b style=\'color:#f0883e\'>" + str(d) + "</b>" if pd.Timestamp(_cal_year, _cal_month, d).date() == _cal_today.date() else str(d)}'
            f'</th>'
            for d in range(1, _cal_days_in_month + 1)
        )
        _cal_html = f"""
        <div style="overflow-x:auto;background:#161b22;padding:12px;border-radius:8px;border:1px solid #30363d">
          <table style="border-collapse:separate;border-spacing:2px;font-family:monospace">
            <thead><tr>
              <th style="color:#8b949e;font-size:10px;padding-right:8px;text-align:left">Campanha</th>
              {_header_cells}
            </tr></thead>
            <tbody>{_cal_rows_html}</tbody>
          </table>
          <div style="margin-top:8px;display:flex;gap:12px">
            {"".join(f'<span style="font-size:10px;color:#8b949e"><span style="display:inline-block;width:10px;height:10px;background:{c};border-radius:2px;margin-right:4px"></span>{s}</span>' for s, c in _STATUS_COLORS.items())}
          </div>
        </div>"""
        import streamlit.components.v1 as _cv1_cal
        _cv1_cal.html(_cal_html, height=max(120, len(_cal_camps_cal) * 22 + 60), scrolling=True)

        # ── Data table + export ───────────────────────────────────────────────
        st.divider()
        st.subheader("📊 Tabela de Dados")

        table_df = filtered[["cliente", "campanha", "data_inicio", "data_fim", "veiculos", "link_plano", "link_dash", "status_campanha", "dias_restantes"]].copy()
        table_df.columns = ["Cliente", "Campanha", "Início", "Fim", "Veículos", "Link Plano", "Link Dash", "Status", "Dias Restantes"]
        st.dataframe(table_df, use_container_width=True, hide_index=True, height=420)
        _export_buttons(table_df, "campanhas_veiculacao", "exp_camp_tbl")

    # ═══════════════════════════════════════════════════════════════════════════
    #  PAGE — GERENCIAR CAMPANHAS (admin/editor)
    # ═══════════════════════════════════════════════════════════════════════════
    elif page == "⚙️ Gerenciar Campanhas":
        _page_header("⚙️", "Gerenciar Campanhas", "Campanhas, veículos, mapeamentos e alertas")

        if role not in ["admin", "editor"]:
            st.warning("🔒 Acesso negado.")
            return

        # ── Veículos pendentes de mapeamento ──────────────────────────────────
        _pending_vehs = get_pending_vehicles()
        if _pending_vehs:
            with st.expander(
                f"⚠️ **{len(_pending_vehs)} veículo(s) pendentes de mapeamento** — clique para ver",
                expanded=True,
            ):
                # Filtros rápidos
                _pv_col1, _pv_col2 = st.columns(2)
                _pv_filter_status = _pv_col1.selectbox(
                    "Filtrar por pendência",
                    ["— todos —", "Sem plano", "Sem assets", "Sem plano e sem assets"],
                    key="pv_filter_status",
                )
                _pv_filter_camp = _pv_col2.text_input(
                    "Filtrar por campanha", key="pv_filter_camp", placeholder="nome…"
                )

                _pv_filtered = _pending_vehs
                if _pv_filter_status == "Sem plano":
                    _pv_filtered = [p for p in _pv_filtered if not p["has_plan"]]
                elif _pv_filter_status == "Sem assets":
                    _pv_filtered = [p for p in _pv_filtered if not p["has_assets"]]
                elif _pv_filter_status == "Sem plano e sem assets":
                    _pv_filtered = [p for p in _pv_filtered if not p["has_plan"] and not p["has_assets"]]
                if _pv_filter_camp.strip():
                    _pv_filtered = [p for p in _pv_filtered if _pv_filter_camp.lower() in p["campaign_name"].lower()]

                for _pv in _pv_filtered:
                    _pv_c1, _pv_c2 = st.columns([6, 2])
                    _plan_badge   = "✅ Plano"   if _pv["has_plan"]   else "❌ Sem plano"
                    _assets_badge = "✅ Assets"  if _pv["has_assets"] else "❌ Sem assets"
                    _plan_color   = "#3fb950" if _pv["has_plan"]   else "#f85149"
                    _assets_color = "#3fb950" if _pv["has_assets"] else "#f85149"
                    _pv_c1.markdown(
                        f"**{_pv['vehicle_name']}**  ·  {_pv['campaign_name']}  ·  `{_pv['client_name'] or '—'}`  "
                        f"<span style='color:{_plan_color}'>{_plan_badge}</span>  "
                        f"<span style='color:{_assets_color}'>{_assets_badge}</span>",
                        unsafe_allow_html=True,
                    )
                    if _pv_c2.button(
                        "🗺 Ir para mapeamento",
                        key=f"pv_goto_{_pv['vehicle_id']}",
                        use_container_width=True,
                    ):
                        st.session_state["page"]              = "📥 Mapeamento & Cruzamento"
                        st.session_state["cfg_campaign_id"]   = _pv["campaign_id"]
                        st.session_state["cfg_campaign_name"] = _pv["campaign_name"]
                        st.session_state["cfg_vehicle_id"]    = _pv["vehicle_id"]
                        st.session_state["cfg_vehicle_name"]  = _pv["vehicle_name"]
                        st.rerun()

                st.caption(f"{len(_pv_filtered)} veículo(s) exibido(s)")

        # ── Item 29: criação em lote via planilha ─────────────────────────────
        with st.expander("📥 Criar campanhas e veículos em lote", expanded=False):
            st.caption(
                "Faça upload de uma planilha com as colunas **nome_campanha**, **cliente** e **veiculos** "
                "(veículos separados por vírgula). Baixe o modelo abaixo para começar."
            )

            # Gera template para download
            import io as _io_batch
            _tpl_buf = _io_batch.BytesIO()
            _tpl_df = pd.DataFrame([
                {"nome_campanha": "Campanha Exemplo A", "cliente": "Cliente PPG",
                 "veiculos": "Google Ads, Meta, TikTok"},
                {"nome_campanha": "Campanha Exemplo B", "cliente": "Cliente PPG",
                 "veiculos": "YouTube"},
                {"nome_campanha": "Campanha Exemplo C", "cliente": "Outro Cliente", "veiculos": ""},
            ])
            with pd.ExcelWriter(_tpl_buf, engine="openpyxl") as _w:
                _tpl_df.to_excel(_w, index=False, sheet_name="Campanhas")
            st.download_button(
                "⬇️ Baixar planilha modelo (.xlsx)",
                _tpl_buf.getvalue(),
                "modelo_lote_campanhas.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="batch_template_dl",
            )

            st.markdown("---")
            _batch_file = st.file_uploader(
                "Upload da planilha preenchida", type=["xlsx", "xls", "csv"],
                key="batch_upload"
            )

            # Parse imediato ao receber o arquivo — salva no session_state para
            # sobreviver aos reruns causados pela interação com os multiselects
            if _batch_file:
                try:
                    if _batch_file.name.lower().endswith(".csv"):
                        _batch_df = pd.read_csv(_batch_file)
                    else:
                        _batch_df = pd.read_excel(_batch_file)
                    _batch_df.columns = [c.strip().lower().replace(" ", "_") for c in _batch_df.columns]

                    if "nome_campanha" not in _batch_df.columns:
                        st.error("Coluna obrigatória ausente: nome_campanha")
                    else:
                        _batch_df = _batch_df.fillna("")
                        _parsed: dict[str, dict] = {}
                        for _, _br in _batch_df.iterrows():
                            _cn = str(_br.get("nome_campanha", "")).strip()
                            _cl = str(_br.get("cliente", "")).strip()
                            _vv = str(_br.get("veiculos", "")).strip()
                            _vs = [v.strip() for v in _vv.split(",") if v.strip()] if _vv else []
                            if not _cn:
                                continue
                            if _cn not in _parsed:
                                _parsed[_cn] = {"cliente": _cl, "veiculos": []}
                            _parsed[_cn]["veiculos"].extend(
                                [v for v in _vs if v not in _parsed[_cn]["veiculos"]]
                            )
                        st.session_state["_batch_parsed"] = _parsed
                except Exception as _batch_err:
                    st.error(f"Erro ao ler planilha: {_batch_err}")
                    st.session_state.pop("_batch_parsed", None)
            elif not _batch_file:
                st.session_state.pop("_batch_parsed", None)

            # Renderiza seleção a partir do session_state (persiste entre reruns)
            _batch_parsed = st.session_state.get("_batch_parsed", {})
            if _batch_parsed:
                st.markdown(f"**{len(_batch_parsed)} campanha(s) encontrada(s)** — selecione os veículos a criar:")
                st.caption("Todos os veículos vêm pré-selecionados. Desmarque os que não quer criar.")

                _batch_selection: dict[str, list[str]] = {}
                for _cn, _cd in _batch_parsed.items():
                    _cl = _cd["cliente"]
                    _vs_all = _cd["veiculos"]
                    st.markdown(f"**{_cn}** · `{_cl or '—'}`")
                    if _vs_all:
                        _sel_vehs = st.multiselect(
                            "Veículos",
                            options=_vs_all,
                            default=_vs_all,
                            key=f"batch_vsel_{_cn}",
                            label_visibility="collapsed",
                        )
                    else:
                        st.caption("Sem veículos na planilha (apenas a campanha será criada).")
                        _sel_vehs = []
                    _batch_selection[_cn] = _sel_vehs

                st.divider()
                _total_vehs_sel = sum(len(v) for v in _batch_selection.values())
                st.caption(f"Total selecionado: **{len(_batch_selection)} campanha(s)** · **{_total_vehs_sel} veículo(s)**")

                if st.button("✅ Criar seleção", type="primary", key="batch_create"):
                    _existing_names = {c["name"].lower(): c["id"] for c in get_campaigns(role="admin", include_archived=True)}
                    _created, _skipped, _vehs_created, _errors_b = 0, 0, 0, []
                    for _cn, _sel_vehs in _batch_selection.items():
                        _cl = _batch_parsed[_cn]["cliente"]
                        try:
                            if _cn.lower() in _existing_names:
                                _cid_b = _existing_names[_cn.lower()]
                                _skipped += 1
                            else:
                                _cid_b = create_campaign(_cn, _cl)
                                _created += 1
                            for _vn in _sel_vehs:
                                try:
                                    create_vehicle(_cid_b, _vn)
                                    _vehs_created += 1
                                except Exception:
                                    pass
                        except Exception as _be:
                            _errors_b.append(f"{_cn}: {_be}")
                    st.success(
                        f"✅ {_created} campanha(s) criada(s), {_skipped} já existia(m). "
                        f"{_vehs_created} veículo(s) adicionado(s)."
                    )
                    if _errors_b:
                        for _eb in _errors_b:
                            st.error(_eb)
                    st.session_state.pop("_batch_parsed", None)
                    st.rerun()

        # ── Item 19: cobertura de mapeamento ──────────────────────────────────
        _cov_data = get_mapping_coverage()
        if _cov_data:
            with st.expander("📊 Cobertura de Mapeamento por Veículo", expanded=False):
                _cov_df = pd.DataFrame(_cov_data)[
                    ["campaign", "vehicle", "plan_mapped", "plan_total", "assets_mapped", "assets_total", "coverage_pct"]
                ].rename(columns={
                    "campaign": "Campanha", "vehicle": "Veículo",
                    "plan_mapped": "Plano Mapeado", "plan_total": "Plano Total",
                    "assets_mapped": "Assets Mapeados", "assets_total": "Assets Total",
                    "coverage_pct": "Cobertura %",
                })
                def _color_cov(val):
                    if val >= 80: return "color:#3fb950"
                    if val >= 50: return "color:#f0883e"
                    return "color:#f85149"
                st.dataframe(
                    _cov_df.style.map(_color_cov, subset=["Cobertura %"]),
                    use_container_width=True, hide_index=True,
                )
            st.divider()

        # ── Item 31: toggle mostrar arquivadas ────────────────────────────────
        _show_archived = st.toggle("Mostrar campanhas arquivadas", value=False, key="show_archived_toggle")
        all_camps = get_campaigns(role="admin", include_archived=_show_archived)
        if not all_camps:
            st.info("Nenhuma campanha cadastrada.")
        else:
            for camp in all_camps:
                cid   = camp["id"]
                cname = camp["name"]
                ccli  = camp.get("client_name", "") or "—"
                _is_archived = camp.get("archived", False)
                vehs  = get_vehicles(cid)

                _arch_badge = " 🗄 *arquivada*" if _is_archived else ""
                with st.expander(f"📢 **{cname}**{_arch_badge}  ·  👤 {ccli}  ·  {len(vehs)} veículo(s)", expanded=False):

                    # ── Renomear campanha ──────────────────────────────────
                    rc1, rc2 = st.columns([5, 1])
                    new_cname = rc1.text_input("Renomear campanha", value=cname, key=f"ren_camp_{cid}")
                    rc2.write(""); rc2.write("")
                    if rc2.button("💾", key=f"save_camp_{cid}", help="Salvar novo nome"):
                        if new_cname.strip() and new_cname.strip() != cname:
                            try:
                                rename_campaign(cid, new_cname.strip())
                                log_audit(username, "renomear", "campanha", cname, f"Novo nome: {new_cname.strip()}")
                                st.success(f"Renomeada para **{new_cname.strip()}**")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erro: {e}")

                    # ── Arquivar / Desarquivar campanha (item 31) ─────────
                    _arch_label = "🔓 Desarquivar campanha" if _is_archived else "🗄 Arquivar campanha"
                    _arch_help  = "Remove do fluxo ativo sem excluir dados" if not _is_archived else "Reativa a campanha"
                    if st.button(_arch_label, key=f"arch_camp_btn_{cid}", help=_arch_help):
                        archive_campaign(cid, not _is_archived)
                        _verb = "arquivar" if not _is_archived else "desarquivar"
                        log_audit(username, _verb, "campanha", cname)
                        st.success(f"{'Arquivada' if not _is_archived else 'Desarquivada'}: **{cname}**")
                        st.rerun()

                    # ── Excluir campanha ───────────────────────────────────
                    if st.button("🗑 Excluir campanha", key=f"del_camp_btn_{cid}"):
                        st.session_state[f"confirm_del_camp_{cid}"] = True

                    if st.session_state.get(f"confirm_del_camp_{cid}"):
                        st.error(
                            f"⚠️ Excluir **{cname}** e todos os seus {len(vehs)} veículo(s)? "
                            "Todos os dados de plano e assets serão perdidos. Não pode ser desfeito."
                        )
                        dc1, dc2 = st.columns(2)
                        if dc1.button("✅ Sim, excluir tudo", key=f"confirm_yes_camp_{cid}", type="primary"):
                            delete_campaign(cid)
                            log_audit(username, "excluir", "campanha", cname, f"{len(vehs)} veículo(s) removidos")
                            st.session_state.pop(f"confirm_del_camp_{cid}", None)
                            st.rerun()
                        if dc2.button("❌ Cancelar", key=f"confirm_no_camp_{cid}"):
                            st.session_state.pop(f"confirm_del_camp_{cid}", None)
                            st.rerun()

                    # ── Limpar dados da campanha (item 21) ────────────────
                    if st.button("🧹 Limpar todos os dados", key=f"clear_data_btn_{cid}",
                                 help="Remove plano e assets de todos os veículos desta campanha"):
                        st.session_state[f"confirm_clear_{cid}"] = True

                    if st.session_state.get(f"confirm_clear_{cid}"):
                        st.warning(
                            f"⚠️ Isso apagará o plano e os assets de **todos os {len(vehs)} veículo(s)** "
                            f"de **{cname}**. O histórico (log) será mantido. Não pode ser desfeito."
                        )
                        cl1, cl2 = st.columns(2)
                        if cl1.button("🧹 Sim, limpar dados", type="primary", key=f"confirm_clear_yes_{cid}"):
                            n = clear_campaign_data(cid)
                            st.session_state.pop(f"confirm_clear_{cid}", None)
                            st.success(f"{n} registro(s) removido(s).")
                            st.rerun()
                        if cl2.button("❌ Cancelar", key=f"confirm_clear_no_{cid}"):
                            st.session_state.pop(f"confirm_clear_{cid}", None)
                            st.rerun()

                    # ── Veículos ───────────────────────────────────────────
                    if vehs:
                        st.markdown("**Veículos**")
                        for v in vehs:
                            vid   = v["id"]
                            vname = v["name"]
                            vc1, vc2, vc3 = st.columns([5, 1, 1])
                            new_vname = vc1.text_input(
                                "", value=vname, key=f"ren_veh_{vid}",
                                label_visibility="collapsed"
                            )
                            vc2.write("")
                            if vc2.button("💾", key=f"save_veh_{vid}", help="Salvar novo nome"):
                                if new_vname.strip() and new_vname.strip() != vname:
                                    try:
                                        rename_vehicle(vid, new_vname.strip())
                                        st.success(f"Veículo renomeado para **{new_vname.strip()}**")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Erro: {e}")
                            if vc3.button("🗑", key=f"del_veh_btn_{vid}", help="Excluir veículo"):
                                st.session_state[f"confirm_del_veh_{vid}"] = True

                            if st.session_state.get(f"confirm_del_veh_{vid}"):
                                st.warning(f"Excluir veículo **{vname}** e seus dados?")
                                dv1, dv2 = st.columns(2)
                                if dv1.button("✅ Sim", key=f"confirm_yes_veh_{vid}", type="primary"):
                                    delete_vehicle(vid)
                                    st.session_state.pop(f"confirm_del_veh_{vid}", None)
                                    st.rerun()
                                if dv2.button("❌ Cancelar", key=f"confirm_no_veh_{vid}"):
                                    st.session_state.pop(f"confirm_del_veh_{vid}", None)
                                    st.rerun()

                            # ── Timestamps (item 11 extra) + Log (item 15) ────
                            _vts = get_ingestion_timestamps(cid, vid)
                            _ts_parts = []
                            if _vts["plan"]:
                                _s = _vts["plan"].strftime("%d/%m/%Y %H:%M") if hasattr(_vts["plan"], "strftime") else str(_vts["plan"])[:16]
                                _ts_parts.append(f"Plano: {_s}" + (f" · {_vts['plan_by']}" if _vts["plan_by"] else ""))
                            if _vts["assets"]:
                                _s = _vts["assets"].strftime("%d/%m/%Y %H:%M") if hasattr(_vts["assets"], "strftime") else str(_vts["assets"])[:16]
                                _ts_parts.append(f"Assets: {_s}" + (f" · {_vts['assets_by']}" if _vts["assets_by"] else ""))
                            if _ts_parts:
                                st.caption("🕐 " + "  ·  ".join(_ts_parts))

                            # ── Item 40: Notas + Histórico em tabs ────────────
                            _tab_notes, _tab_hist = st.tabs(["💬 Notas", "📋 Histórico"])

                            with _tab_notes:
                                _notes = get_vehicle_notes(vid)
                                if _notes:
                                    for _nt in _notes:
                                        _nt_ts = _nt["created_at"].strftime("%d/%m/%Y %H:%M") if hasattr(_nt["created_at"], "strftime") else str(_nt["created_at"])[:16]
                                        _nc1, _nc2 = st.columns([9, 1])
                                        _nc1.markdown(
                                            f"<small style='color:#8b949e'>{_nt['username']} · {_nt_ts}</small><br>{_nt['note']}",
                                            unsafe_allow_html=True,
                                        )
                                        if _nc2.button("🗑", key=f"del_note_{_nt['id']}", help="Excluir nota"):
                                            delete_vehicle_note(_nt["id"])
                                            st.rerun()
                                else:
                                    st.caption("Nenhuma nota registrada.")
                                _new_note = st.text_area(
                                    "Nova nota", key=f"note_input_{vid}", height=80,
                                    placeholder="Observação, ocorrência, contexto…",
                                    label_visibility="collapsed",
                                )
                                if st.button("💬 Salvar nota", type="primary", key=f"note_save_{vid}"):
                                    if _new_note.strip():
                                        add_vehicle_note(vid, cid, username, _new_note.strip())
                                        st.rerun()

                            with _tab_hist:
                                _log = get_ingestion_log(cid, vid, limit=20)
                                if not _log:
                                    st.caption("Nenhuma atualização registrada.")
                                else:
                                    for _e in _log:
                                        _ts_str = _e["ts"].strftime("%d/%m/%Y %H:%M") if _e["ts"] and hasattr(_e["ts"], "strftime") else str(_e["ts"] or "")[:16]
                                        _dtype_lbl = "Plano" if _e["data_type"] == "plan" else "Assets"
                                        _hc1, _hc2 = st.columns([6, 1])
                                        _hc1.caption(
                                            f"**{_ts_str}** · {_dtype_lbl} · "
                                            f"{_e['row_count']:,} linhas · "
                                            f"{'🔒 ' if _e.get('username') else ''}"
                                            f"{_e.get('username') or '—'}"
                                        )
                                        _has_blob = _e.get("id") is not None
                                        if _has_blob and _hc2.button("↩", key=f"rb_{_e['id']}", help="Restaurar esta versão"):
                                            st.session_state[f"confirm_rb_{_e['id']}"] = True
                                        if st.session_state.get(f"confirm_rb_{_e['id']}"):
                                            st.warning(f"Restaurar versão de {_ts_str} ({_dtype_lbl}, {_e['row_count']:,} linhas)?")
                                            _rb1, _rb2 = st.columns(2)
                                            if _rb1.button("✅ Restaurar", type="primary", key=f"rb_yes_{_e['id']}"):
                                                try:
                                                    restore_ingestion_from_log(_e["id"])
                                                    st.session_state.pop(f"confirm_rb_{_e['id']}", None)
                                                    st.success("✅ Versão restaurada com sucesso!")
                                                    st.rerun()
                                                except Exception as _rb_exc:
                                                    st.error(str(_rb_exc))
                                            if _rb2.button("❌ Cancelar", key=f"rb_no_{_e['id']}"):
                                                st.session_state.pop(f"confirm_rb_{_e['id']}", None)
                                                st.rerun()
                                        st.markdown("---")
                    else:
                        st.caption("Sem veículos cadastrados.")

                    # ── Item 18: alertas configuráveis por campanha ────────
                    if role == "admin":
                        with st.expander("🔔 Alertas de email para esta campanha", expanded=False):
                            _a_configs = get_alert_configs(cid)
                            ALERT_LABELS = {
                                "ending_soon": "⏰ Encerrando em breve",
                                "no_assets":   "⚠️ Sem assets cadastrados",
                                "no_plan":     "⚠️ Sem plano cadastrado",
                                "over_budget": "💸 Acima do orçamento (%)",
                            }
                            _existing = {a["alert_type"]: a for a in _a_configs}

                            for _atype, _alabel in ALERT_LABELS.items():
                                _ae = _existing.get(_atype)
                                st.markdown(f"**{_alabel}**")
                                _ka1, _ka2, _ka3, _ka4 = st.columns([3, 2, 2, 1])
                                _thr_default = _ae["threshold"] if _ae else (7 if "soon" in _atype else 100)
                                _email_default = _ae["email_to"] if _ae else ""
                                _enabled_default = _ae["enabled"] if _ae else False
                                _thr   = _ka1.number_input("Dias/%" if "soon" in _atype or "budget" in _atype else "—",
                                                           min_value=1, max_value=365, value=_thr_default,
                                                           key=f"al_thr_{cid}_{_atype}", label_visibility="collapsed")
                                _email = _ka2.text_input("Email destino", value=_email_default,
                                                         placeholder="email@exemplo.com",
                                                         key=f"al_email_{cid}_{_atype}", label_visibility="collapsed")
                                _enab  = _ka3.checkbox("Ativado", value=_enabled_default,
                                                        key=f"al_enab_{cid}_{_atype}")
                                _ka4.write("")
                                if _ka4.button("💾", key=f"al_save_{cid}_{_atype}", help="Salvar alerta"):
                                    if _email and "@" not in _email:
                                        st.error(f"E-mail inválido: **{_email}**. Use o formato usuario@dominio.com.")
                                    elif _ae:
                                        update_alert_config(_ae["id"], int(_thr), _email, _enab)
                                    else:
                                        save_alert_config(cid, _atype, int(_thr), _email, _enab,
                                                          created_by=username)
                                    st.success("Alerta salvo!")
                                    st.rerun()
                                if _ae and st.button("🗑 Remover", key=f"al_del_{cid}_{_atype}"):
                                    delete_alert_config(_ae["id"])
                                    st.rerun()
                                st.markdown("---")

    # ═══════════════════════════════════════════════════════════════════════════
    #  PAGE — RELATÓRIO SOB DEMANDA (item 26)
    # ═══════════════════════════════════════════════════════════════════════════
    elif page == "📄 Relatório":
        import streamlit.components.v1 as _stc
        _page_header("📄", "Relatório de Campanhas", "Gere e exporte o relatório consolidado")

        if st.button("🔄 Gerar relatório agora", type="primary", key="rpt_generate"):
            st.session_state.pop("_rpt_html", None)

        if "_rpt_html" not in st.session_state:
            with st.spinner("Gerando relatório…"):
                try:
                    import sys as _sys, os as _os
                    _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
                    from report import gather_plan_data, deduplicate, compute_status, build_html
                    _raw, _no_data = gather_plan_data()
                    if not _raw.empty:
                        _raw = deduplicate(_raw)
                        _df_rpt = compute_status(_raw)
                    else:
                        _df_rpt = _raw
                    st.session_state["_rpt_html"] = build_html(_df_rpt, _no_data)
                except Exception as _rpt_err:
                    st.error(f"Erro ao gerar relatório: {_rpt_err}")

        _html_rpt = st.session_state.get("_rpt_html")
        if _html_rpt:
            st.download_button(
                "⬇️ Baixar HTML",
                _html_rpt.encode("utf-8"),
                f"relatorio_{datetime.now().strftime('%Y%m%d_%H%M')}.html",
                "text/html",
                key="rpt_download",
            )
            _stc.html(_html_rpt, height=800, scrolling=True)

    # ═══════════════════════════════════════════════════════════════════════════
    #  PAGE 3 — CLIENTES (admin only)
    # ═══════════════════════════════════════════════════════════════════════════
    elif page == "🏢 Clientes":
        _page_header("🏢", "Clientes", "Gerencie os clientes e suas campanhas")

        if role not in ["admin", "editor"]:
            st.warning("🔒 Acesso negado.")
            return
        
        with st.expander("➕ Adicionar novo cliente", expanded=False):
            new_cli = st.text_input("Nome do Cliente", key="nc_name")
            if st.button("Adicionar cliente", type="primary", key="nc_create"):
                if new_cli.strip():
                    try:
                        add_client(new_cli.strip())
                        st.success(f"Cliente **{new_cli.strip()}** adicionado.")
                        st.rerun()
                    except Exception:
                        st.error("Erro ao adicionar cliente (pode já existir).")
                else:
                    st.warning("Preencha o nome do cliente.")
        
        st.divider()
        clients = get_clients()
        
        if not clients:
            st.info("Nenhum cliente cadastrado.")
        else:
            all_campaigns = get_campaigns(role="admin")
            camp_counts = {}
            for camp in all_campaigns:
                cname = camp.get("client_name", "")
                camp_counts[cname] = camp_counts.get(cname, 0) + 1

            for c in clients:
                with st.container():
                    cc1, cc2, cc3 = st.columns([6, 1, 1])
                    cc1.markdown(f"**{c}**")
                    qtd = camp_counts.get(c, 0)
                    cc1.caption(f"{qtd} campanha(s) atrelada(s)")

                    if cc2.button("✏️ Renomear", key=f"ren_cli_{c}"):
                        st.session_state[f"edit_cli_{c}"] = not st.session_state.get(f"edit_cli_{c}", False)
                        st.session_state.pop(f"confirm_del_cli_{c}", None)

                    if cc3.button("🗑 Excluir", key=f"del_cli_{c}"):
                        st.session_state[f"confirm_del_cli_{c}"] = True
                        st.session_state.pop(f"edit_cli_{c}", None)

                    # Confirmação de exclusão
                    if st.session_state.get(f"confirm_del_cli_{c}"):
                        st.warning(
                            f"⚠️ Excluir **{c}**? Isso desvincula {qtd} campanha(s). Não pode ser desfeito."
                        )
                        dc1, dc2 = st.columns(2)
                        if dc1.button("✅ Sim, excluir", key=f"confirm_yes_cli_{c}", type="primary"):
                            delete_client(c)
                            st.rerun()
                        if dc2.button("❌ Cancelar", key=f"confirm_no_cli_{c}"):
                            st.session_state.pop(f"confirm_del_cli_{c}", None)
                            st.rerun()

                    if st.session_state.get(f"edit_cli_{c}", False):
                        rc1, rc2 = st.columns([6, 2])
                        novo_nome = rc1.text_input("Novo nome:", value=c, key=f"new_name_{c}")
                        if rc2.button("Salvar", key=f"save_ren_{c}"):
                            if novo_nome.strip() and novo_nome.strip() != c:
                                rename_client(c, novo_nome.strip())
                                st.rerun()
                st.markdown("---")

    # ═══════════════════════════════════════════════════════════════════════════
    #  PAGE 4 — USUÁRIOS  (admin only)
    # ═══════════════════════════════════════════════════════════════════════════
    elif page == "👥 Usuários":
        _page_header("👥", "Usuários", "Gerencie acessos, perfis e destinatários de relatório")

        if role not in ["admin", "editor"]:
            st.warning("🔒 Acesso negado.")
            return

        # ── Criar novo usuário ────────────────────────────────────────────────
        with st.expander("➕ Criar novo usuário", expanded=False):
            nu1, nu2, nu3 = st.columns(3)
            new_uname = nu1.text_input("Usuário", key="nu_name")
            new_pw    = nu2.text_input("Senha",   key="nu_pw",   type="password")
            new_role  = nu3.selectbox("Perfil",   ["viewer", "editor", "admin"], key="nu_role")
            new_email = st.text_input("E-mail (para receber relatórios)", key="nu_email", placeholder="usuario@exemplo.com")
            if st.button("Criar usuário", type="primary", key="nu_create"):
                if new_uname.strip() and new_pw.strip():
                    try:
                        add_user(new_uname.strip(), new_pw.strip(), new_role, email=new_email.strip())
                        st.success(f"Usuário **{new_uname}** criado.")
                        st.rerun()
                    except Exception as e:
                        st.error("Usuário já existe." if "UNIQUE" in str(e) else str(e))
                else:
                    st.warning("Preencha usuário e senha.")

        st.divider()

        # ── Lista de usuários ─────────────────────────────────────────────────
        users   = get_users()
        clients = get_clients()

        for u in users:
            uname = u["username"]
            urole = u["role"]
            is_self = uname == username

            _uemail = u.get("email", "")
            _email_tag = f"  ·  ✉️ {_uemail}" if _uemail else ""
            with st.expander(f"{'🔑' if urole == 'admin' else '👤'} **{uname}**  ·  `{urole.upper()}`{_email_tag}", expanded=False):
                ec1, ec2 = st.columns(2)

                # Editar perfil e senha
                with ec1:
                    st.markdown("**Editar perfil**")
                    new_role_sel = st.selectbox(
                        "Perfil", ["viewer", "editor", "admin"],
                        index=["viewer", "editor", "admin"].index(urole) if urole in ["viewer", "editor", "admin"] else 0,
                        key=f"eu_role_{uname}",
                        disabled=is_self,
                    )
                    new_pw_val = st.text_input(
                        "Nova senha (deixe em branco para não alterar)",
                        type="password", key=f"eu_pw_{uname}",
                    )
                    new_email_val = st.text_input(
                        "E-mail", value=_uemail, key=f"eu_email_{uname}",
                        placeholder="usuario@exemplo.com",
                    )
                    bc1, bc2 = st.columns(2)
                    if bc1.button("💾 Salvar", type="primary", key=f"eu_save_{uname}"):
                        update_user(
                            uname,
                            new_password=new_pw_val.strip() or None,
                            new_role=new_role_sel if not is_self else None,
                            new_email=new_email_val.strip(),
                        )
                        st.success("Usuário atualizado.")
                        st.rerun()
                    if bc2.button("🗑 Excluir", key=f"eu_del_{uname}", disabled=is_self,
                                  type="secondary"):
                        delete_user(uname)
                        st.warning(f"Usuário **{uname}** removido.")
                        st.rerun()

                # Clientes permitidos
                with ec2:
                    st.markdown("**Clientes com acesso** _(admin acessa tudo)_" if urole == "admin"
                                else "**Clientes com acesso**")
                    if urole != "admin":
                        current_clients = get_user_clients(uname)
                        if clients:
                            sel_clients = st.multiselect(
                                "Selecionar clientes",
                                options=clients,
                                default=[c for c in current_clients if c in clients],
                                key=f"eu_cli_{uname}",
                            )
                            if st.button("Salvar acesso", key=f"eu_cli_save_{uname}"):
                                set_user_clients(uname, sel_clients)
                                st.success("Acesso atualizado.")
                                st.rerun()
                        else:
                            st.info("Nenhum cliente cadastrado no Gerenciador de Clientes.")
                    else:
                        st.caption("Admins visualizam todas as campanhas independente do cliente.")

        # ── Destinatários do relatório diário ─────────────────────────────────
        if role == "admin":
            st.divider()
            st.subheader("📧 Destinatários do Relatório Diário")
            st.caption(
                "Configure quais e-mails recebem o relatório por cliente. "
                "Usuários com e-mail cadastrado e cliente associado também recebem automaticamente."
            )

            _rr_clients = get_clients()
            if not _rr_clients:
                st.info("Nenhum cliente cadastrado.")
            else:
                _rr_sel_client = st.selectbox(
                    "Filtrar por cliente", ["— todos —"] + _rr_clients, key="rr_client_filter"
                )
                _rr_list = get_report_recipients(
                    None if _rr_sel_client == "— todos —" else _rr_sel_client
                )

                if _rr_list:
                    for _rr in _rr_list:
                        _rc1, _rc2, _rc3 = st.columns([4, 1, 1])
                        _rc1.write(f"**{_rr['email']}**  ·  `{_rr['client_name']}`")
                        _active_label = "✅ Ativo" if _rr["active"] else "⏸ Pausado"
                        if _rc2.button(_active_label, key=f"rr_tog_{_rr['id']}"):
                            toggle_report_recipient(_rr["id"], not _rr["active"])
                            st.rerun()
                        if _rc3.button("🗑", key=f"rr_del_{_rr['id']}", help="Remover destinatário"):
                            delete_report_recipient(_rr["id"])
                            st.rerun()
                else:
                    st.caption("Nenhum destinatário cadastrado para este filtro.")

                st.markdown("**Adicionar destinatário**")
                _ra1, _ra2, _ra3 = st.columns([2, 3, 1])
                _rr_new_client = _ra1.selectbox("Cliente", _rr_clients, key="rr_new_client")
                _rr_new_email  = _ra2.text_input("E-mail", key="rr_new_email", placeholder="destinatario@exemplo.com")
                _ra3.write(""); _ra3.write("")
                if _ra3.button("➕ Add", type="primary", key="rr_add"):
                    if _rr_new_email.strip():
                        if "@" not in _rr_new_email:
                            st.error("E-mail inválido. Use o formato usuario@dominio.com.")
                        else:
                            add_report_recipient(_rr_new_client, _rr_new_email.strip())
                            st.success(f"✅ Adicionado: {_rr_new_email}")
                            st.rerun()
                    else:
                        st.warning("Informe um e-mail.")

        # ── Item 42: Timeout de sessão por inatividade ────────────────────────
        if role == "admin":
            st.divider()
            st.subheader("🔐 Segurança da Sessão")
            _cur_timeout = int(get_system_config("session_timeout_hours", "8"))
            _new_timeout = st.number_input(
                "Tempo máximo de inatividade (horas)",
                min_value=1, max_value=168, value=_cur_timeout, step=1,
                help="Sessões sem atividade por mais deste tempo serão encerradas automaticamente.",
                key="session_timeout_input",
            )
            if st.button("💾 Salvar timeout", type="primary", key="save_timeout"):
                set_system_config("session_timeout_hours", str(_new_timeout))
                st.success(f"✅ Timeout atualizado para {_new_timeout}h.")

        # ── Item 43: Histórico de logins por usuário ──────────────────────────
        if role == "admin":
            st.divider()
            st.subheader("🔑 Histórico de Logins Recentes")
            _lh_all = get_login_history(limit=100)
            if _lh_all:
                _lh_df = pd.DataFrame(_lh_all)
                _lh_df["ts"] = pd.to_datetime(_lh_df["ts"]).dt.strftime("%d/%m/%Y %H:%M:%S")
                _lh_df["resultado"] = _lh_df["success"].map({True: "✅ Sucesso", False: "❌ Falha"})
                st.dataframe(
                    _lh_df[["ts", "username", "resultado"]].rename(columns={
                        "ts": "Data/Hora", "username": "Usuário", "resultado": "Resultado"
                    }),
                    use_container_width=True, hide_index=True, height=300,
                )
            else:
                st.caption("Nenhum login registrado ainda.")

    # ═══════════════════════════════════════════════════════════════════════════
    #  PAGE — AUDITORIA (admin only)
    # ═══════════════════════════════════════════════════════════════════════════
    elif page == "📋 Auditoria":
        _page_header("📋", "Auditoria", "Histórico de ações realizadas no sistema")

        if role != "admin":
            st.warning("🔒 Acesso negado.")
            return

        _aud_c1, _aud_c2, _aud_c3 = st.columns(3)
        _aud_entity = _aud_c1.selectbox(
            "Filtrar por tipo",
            ["— todos —", "campanha", "veículo", "usuário", "cliente", "dados", "login", "configuração"],
            key="aud_entity_filter",
        )
        _aud_user_filter = _aud_c2.text_input("Filtrar por usuário", key="aud_user_filter", placeholder="username")
        _aud_limit = _aud_c3.number_input("Máx. registros", min_value=50, max_value=1000, value=200, step=50, key="aud_limit")

        _aud_logs = get_audit_log(
            limit=int(_aud_limit),
            entity_type=None if _aud_entity == "— todos —" else _aud_entity,
            username=_aud_user_filter.strip() or None,
        )

        if not _aud_logs:
            st.info("Nenhum registro de auditoria encontrado.")
        else:
            _aud_df = pd.DataFrame(_aud_logs)
            _aud_df["ts"] = pd.to_datetime(_aud_df["ts"]).dt.strftime("%d/%m/%Y %H:%M:%S")
            st.caption(f"**{len(_aud_df)}** registro(s)")
            st.dataframe(
                _aud_df[["ts", "username", "action", "entity_type", "entity_name", "details"]].rename(columns={
                    "ts": "Data/Hora", "username": "Usuário", "action": "Ação",
                    "entity_type": "Tipo", "entity_name": "Entidade", "details": "Detalhes",
                }),
                use_container_width=True, hide_index=True, height=520,
            )
            _export_buttons(_aud_df, "auditoria", "exp_audit")


if __name__ == "__main__":
    main()
