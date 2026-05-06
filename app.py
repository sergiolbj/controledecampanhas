import json # Reload trigger 1

from datetime import datetime, timedelta

import extra_streamlit_components as stx  # noqa: F401 (used via _cookie_manager())
import pandas as pd
import plotly.express as px
import streamlit as st

from auth import (
    get_db, init_db, login_ui, logout,
    get_campaigns, create_campaign, update_campaign_client, get_vehicles, create_vehicle,
    save_ingestion, load_ingestion, save_user_state, load_user_state,
    get_users, add_user, update_user, delete_user,
    get_clients, add_client, delete_client, rename_client, get_user_clients, set_user_clients,
    create_session, validate_session, delete_session,
    save_campaign_sheets_config, load_campaign_sheets_config,
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
    page_title="AdOps Control Center",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
[data-testid="stAppViewContainer"] { background: #0d1117; }
[data-testid="stSidebar"]          { background: #161b22; border-right: 1px solid #30363d; }
.block-container                   { padding-top: 1.5rem; }
</style>
""", unsafe_allow_html=True)


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
            h_start = hr1.number_input("Cabeçalho — linha inicial", 1, 1000, 1, key=f"{prefix}_hrow_s")
            h_end   = hr2.number_input("Cabeçalho — linha final", int(h_start), 1000, int(h_start), key=f"{prefix}_hrow_e")
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
            h_start = ur1.number_input("Cabeçalho — linha inicial", 1, 1000, 1, key=f"{prefix}_hrow_us")
            h_end   = ur2.number_input("Cabeçalho — linha final", int(h_start), 1000, int(h_start), key=f"{prefix}_hrow_ue")
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

        # ── Carregar template (topo, antes dos selectboxes) ───────────────────
        if role == "admin":
            with st.expander("📂 Carregar template salvo", expanded=False):
                client = st.text_input("Cliente", key=f"{prefix}_cli")
                if client:
                    templates = load_templates(client)
                    if templates:
                        tl1, tl2 = st.columns([4, 1])
                        sel_tpl = tl1.selectbox(
                            "Template", ["—"] + list(templates.keys()),
                            key=f"{prefix}_tload",
                        )
                        tl2.write(""); tl2.write("")
                        if tl2.button("📂 Aplicar", key=f"{prefix}_tapply"):
                            if sel_tpl != "—":
                                tpl_map = templates[sel_tpl]["mapping"]
                                cols_available = ["(não mapear)"] + list(df.columns)
                                # Grava diretamente nos keys dos selectboxes para sobrescrever
                                # o valor atual armazenado no session_state
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

        # ── Salvar template atual ─────────────────────────────────────────────
        if role == "admin":
            st.markdown("---")
            sv1, sv2 = st.columns([4, 1])
            tpl_name = sv1.text_input(
                "Salvar mapeamento atual como template",
                placeholder="Nome do template",
                key=f"{prefix}_tname",
            )
            sv2.write(""); sv2.write("")
            if sv2.button("💾 Salvar", key=f"{prefix}_tsave"):
                client_val = st.session_state.get(f"{prefix}_cli", "").strip()
                if client_val and tpl_name.strip():
                    save_template(client_val, tpl_name.strip(), src, mapping)
                    st.success(f"Template **{tpl_name}** salvo!")
                else:
                    st.warning("Abra **Carregar template** acima, preencha o Cliente e informe o nome.")

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

    # Use a compound row label to separate vehicles into distinct rows
    plot["row_label"] = base_y.str.strip() + "  ·  " + plot["vehicle"].astype(str).str.strip()
    
    # Sort to ensure consistent ordering
    plot = plot.sort_values(by=["row_label"]).reset_index(drop=True)
    row_labels_ordered = plot["row_label"].unique().tolist()
    y_col = "row_label"

    hover_cols = [
        c for c in ["sys_campaign", "campaign_name", "asset_id", "format", "status", "asset_link"]
        if c in plot.columns
    ]

    fig = px.timeline(
        plot,
        x_start="start_date",
        x_end="end_date",
        y=y_col,
        color="vehicle",
        text="vehicle",
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
        st.markdown("## 📊 AdOps Control")
        st.caption(f"👤 **{username}** · `{role.upper()}`")
        st.divider()
        if "page" not in st.session_state:
            st.session_state["page"] = "📊 Dashboard"

        # ── Bloco principal: visualização ──────────────────────────────────
        if st.button("📊 Dashboard", use_container_width=True):
            st.session_state["page"] = "📊 Dashboard"
            st.rerun()

        if st.button("📡 Campanhas em Veiculação", use_container_width=True):
            st.session_state["page"] = "📡 Campanhas em Veiculação"
            st.rerun()

        # ── Bloco de configuração (admin/editor) ──────────────────────────
        if role in ["admin", "editor"]:
            st.divider()
            st.caption("⚙️ CONFIGURAÇÃO")

            if st.button("📥 Mapeamento & Cruzamento", use_container_width=True):
                st.session_state["page"] = "📥 Mapeamento & Cruzamento"
                for k in ["cfg_campaign_id", "cfg_campaign_name", "cfg_vehicle_id", "cfg_vehicle_name",
                          "plan_df", "assets_df", "merged_df", "unmatched_df", "fuzzy_df"]:
                    st.session_state.pop(k, None)
                st.rerun()

            if st.button("🏢 Clientes", use_container_width=True):
                st.session_state["page"] = "🏢 Clientes"
                st.rerun()
            if st.button("👥 Usuários", use_container_width=True):
                st.session_state["page"] = "👥 Usuários"
                st.rerun()

        page = st.session_state["page"]
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
        st.title("📥 Ingestão e Mapeamento de Dados")

        if role not in ["admin", "editor"]:
            st.warning("🔒 Somente administradores ou editores podem ingerir dados.")
            return

        # ── Wizard step indicator ─────────────────────────────────────────────
        has_campaign = "cfg_campaign_id" in st.session_state
        has_vehicle  = "cfg_vehicle_id"  in st.session_state
        step = 3 if (has_campaign and has_vehicle) else (2 if has_campaign else 1)

        _step_bar(step)
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
            b1.caption(f"📢 **{camp_name}** › 📺 **{veh_name}**")
            if b2.button("← Alterar veículo", key="back_veh"):
                for k in ["cfg_vehicle_id", "cfg_vehicle_name",
                           "plan_df", "assets_df", "merged_df", "unmatched_df", "fuzzy_df"]:
                    st.session_state.pop(k, None)
                st.rerun()

            tab_plan, tab_assets = st.tabs(["📋 Plano de Conteúdo", "🎨 Base de Assets"])

            with tab_plan:
                if st.session_state.get("plan_source"):
                    st.info(f"💾 Origem salva: **{st.session_state['plan_source']}**")
                plan_df, plan_map, veh_col, veh_filter, plan_source, plan_config = mapper_ui(
                    "Plano de Conteúdo", "plan", PLAN_FIELDS, role
                )
                if plan_df is not None:
                    if st.button("✅ Confirmar Plano", type="primary", key="confirm_plan"):
                        mapped = plan_df.copy()
                        if veh_col != "(não usar)" and veh_filter.strip():
                            mask = (
                                mapped[veh_col].astype(str).str.strip().str.lower()
                                == veh_filter.strip().lower()
                            )
                            mapped = mapped[mask].copy()
                        if veh_col != "(não usar)" and veh_col in mapped.columns:
                            mapped = mapped.rename(columns={veh_col: "vehicle"})
                        active = {k: v for k, v in plan_map.items() if v != "(não mapear)"}
                        mapped = normalize_dates(apply_mapping(mapped, active), ["start_date", "end_date"])
                        st.session_state["plan_df"]      = mapped
                        st.session_state["plan_mapping"] = plan_map
                        st.session_state["plan_source"]  = plan_source
                        st.session_state["plan_config"]  = plan_config
                        save_ingestion(
                            st.session_state["cfg_campaign_id"],
                            st.session_state["cfg_vehicle_id"],
                            "plan", mapped, plan_map, plan_source, json.dumps(plan_config)
                        )
                        st.success(f"Plano confirmado e salvo: {len(mapped):,} registros.")

            with tab_assets:
                if st.session_state.get("assets_source"):
                    st.info(f"💾 Origem salva: **{st.session_state['assets_source']}**")
                assets_df, assets_map, _, _, assets_source, assets_config = mapper_ui(
                    "Base de Assets", "assets", ASSET_FIELDS, role
                )
                if assets_df is not None:
                    if st.button("✅ Confirmar Assets", type="primary", key="confirm_assets"):
                        active = {k: v for k, v in assets_map.items() if v != "(não mapear)"}
                        mapped = apply_mapping(assets_df, active)
                        st.session_state["assets_df"]      = mapped
                        st.session_state["assets_mapping"] = assets_map
                        st.session_state["assets_source"]  = assets_source
                        st.session_state["assets_config"]  = assets_config
                        save_ingestion(
                            st.session_state["cfg_campaign_id"],
                            st.session_state["cfg_vehicle_id"],
                            "assets", mapped, assets_map, assets_source, json.dumps(assets_config)
                        )
                        st.success(f"Assets confirmados e salvos: {len(mapped):,} registros.")

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
                    fuzzy_threshold = cx1.slider("Threshold Fuzzy (%)", 50, 100, 80, key="auto_thresh")
                    use_fuzzy_merge = cx2.checkbox("🔀 Correspondência fuzzy", value=True, key="auto_fuzzy")

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
                        st.download_button("⬇️ Exportar CSV",
                            merged.to_csv(index=False).encode("utf-8"), "merged.csv", "text/csv")

                    with t_miss:
                        if unmatched.empty:
                            st.success("🎉 Todas as linhas do plano foram correspondidas!")
                        else:
                            st.dataframe(unmatched, use_container_width=True, height=420, hide_index=True)
                            st.download_button("⬇️ Exportar Sem Match",
                                unmatched.to_csv(index=False).encode("utf-8"), "unmatched.csv", "text/csv")

                    with t_alert:
                        if alerts.empty:
                            st.success("Nenhuma peça ativa além da data de fim.")
                        else:
                            st.warning(f"**{len(alerts):,}** registro(s) com impressões/gasto após a data de fim.")
                            ac = [c for c in ["Status","Veículo","Campanha","Grupo de Anúncio",
                                              "Anúncio","Fim Plano","Última Veiculação",
                                              "Impressões","Valor Gasto (R$)"] if c in alerts.columns]
                            st.dataframe(
                                alerts[ac].style.applymap(
                                    lambda _: "background-color:#3d1f00;color:#ffa657",
                                    subset=["Status"] if "Status" in ac else []),
                                use_container_width=True, height=420, hide_index=True)
                            st.download_button("⬇️ Exportar Alertas",
                                alerts[ac].to_csv(index=False).encode("utf-8"), "alertas.csv", "text/csv")

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
        d1, d2 = st.columns([3, 1])
        d1.title("📊 Dashboard & Timeline de Veiculação")

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
                with st.spinner("Sincronizando com Google Sheets (todos os veículos)..."):
                    try:
                        def _sync_dtype_list(dtype, configs):
                            all_dfs = []
                            new_configs = []
                            for c_dict in configs:
                                veh_id   = c_dict.get("veh_id")
                                veh_name = c_dict.get("veh_name", "Desconhecido")
                                cfg      = c_dict.get("cfg", {})
                                mapping  = c_dict.get("mapping", {})
                                src_info = c_dict.get("src_info", "")
                                c_id     = c_dict.get("camp_id") or st.session_state.get("cfg_campaign_id")

                                if not veh_id:
                                    continue

                                if not cfg or cfg.get("src") != "Link (Google Sheets / Office 365)":
                                    df, _, _, _, _ = load_ingestion(c_id, veh_id, dtype)
                                    if df is not None and not df.empty:
                                        df = df.copy()
                                        df["vehicle"] = veh_name
                                        all_dfs.append(df)
                                    new_configs.append(c_dict)
                                    continue

                                from data_processor import read_file, apply_mapping, normalize_dates
                                df = read_file("url", url=cfg["url"], sheet_name=cfg.get("sheet", 0), header_row=cfg.get("header_row", 0))
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

                                # Only persist and use result if it has actual rows
                                if not df.empty:
                                    save_ingestion(c_id, veh_id, dtype, df, mapping, src_info, json.dumps(cfg))
                                    all_dfs.append(df)
                                new_configs.append(c_dict)

                            if all_dfs:
                                st.session_state[f"{dtype}_df"] = pd.concat(all_dfs, ignore_index=True)
                                st.session_state[f"all_{dtype}_configs"] = new_configs

                        if sync_p: _sync_dtype_list("plan", sync_p)
                        if sync_a: _sync_dtype_list("assets", sync_a)

                        for k in ["merged_df", "unmatched_df", "fuzzy_df", "_cross_sig"]:
                            st.session_state.pop(k, None)

                        st.success("Sincronizado com sucesso!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro na sincronização: {e}")

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
                            dfs_list.append(df)
                            cfgs_list.append({
                                "camp_id":  camp_id_loop,
                                "veh_id":   veh_id,
                                "veh_name": veh_name,
                                "cfg":      cfg,
                                "mapping":  mapping,
                                "src_info": src_info,
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

            sel_client     = f1.selectbox("Cliente", _opts("sys_client"), key="f_cli")
            sel_sys_camp   = f2.selectbox("Campanha (Sistema)", _opts("sys_campaign"), key="f_scamp")
            sel_asset_camp = f3.selectbox("Campanha (Assets)", _opts("campaign_name_asset"), key="f_acamp")
            sel_vehicle    = f4.selectbox("Veículo",  _opts("vehicle"),       key="f_veh")
            sel_vstatus    = f5.selectbox("Status",   _opts("veiculacao_status"), key="f_sts")

        filtered = base.copy()
        for col, sel in [
            ("sys_client",          sel_client),
            ("sys_campaign",        sel_sys_camp),
            ("campaign_name_asset", sel_asset_camp),
            ("vehicle",             sel_vehicle),
            ("veiculacao_status",   sel_vstatus),
        ]:
            if sel != "(Todos)" and col in filtered.columns:
                filtered = filtered[filtered[col].astype(str) == sel]

        st.caption(f"Exibindo **{len(filtered):,}** de **{len(base):,}** registros")

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
    
            has_status  = "veiculacao_status" in filtered.columns
            has_vehicle = "vehicle" in filtered.columns
    
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
                        vc = filtered["vehicle"].value_counts().reset_index()
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
        ordered = [c for c in TABLE_COLS if c in filtered.columns]
        rest    = [c for c in filtered.columns if c not in ordered]
        tbl = filtered[ordered + rest].rename(columns=TABLE_COLS)

        st.dataframe(tbl, use_container_width=True, hide_index=True, height=420)
        st.download_button(
            "⬇️ Exportar CSV",
            tbl.to_csv(index=False).encode("utf-8"),
            "criativos.csv", "text/csv",
        )


    # ═══════════════════════════════════════════════════════════════════════════
    #  PAGE — CAMPANHAS EM VEICULAÇÃO
    # ═══════════════════════════════════════════════════════════════════════════
    elif page == "📡 Campanhas em Veiculação":
        st.title("📡 Controle de Campanhas em Veiculação")

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
            st.info("A planilha do Google Sheets ainda não foi configurada. Solicite a um administrador.")
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
                    "no módulo de <b>Mapeamento & Cruzamento</b>. Cadastre-os para ter os dados completos.</p>",
                    unsafe_allow_html=True,
                )
                missing_df = pd.DataFrame(missing)
                missing_df.columns = ["Cliente", "Campanha", "Veículo", "Status"]
                st.dataframe(
                    missing_df.style.applymap(
                        lambda _: "color:#f0883e;font-weight:600",
                        subset=["Status"],
                    ),
                    use_container_width=True, hide_index=True,
                )

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

        # ── Data table + export ───────────────────────────────────────────────
        st.divider()
        st.subheader("📊 Tabela de Dados")

        table_df = filtered[["cliente", "campanha", "data_inicio", "data_fim", "veiculos", "link_plano", "link_dash", "status_campanha", "dias_restantes"]].copy()
        table_df.columns = ["Cliente", "Campanha", "Início", "Fim", "Veículos", "Link Plano", "Link Dash", "Status", "Dias Restantes"]
        st.dataframe(table_df, use_container_width=True, hide_index=True, height=420)

        st.download_button(
            "⬇️ Exportar CSV",
            table_df.to_csv(index=False).encode("utf-8"),
            "campanhas_veiculacao.csv", "text/csv",
        )

    # ═══════════════════════════════════════════════════════════════════════════
    #  PAGE 3 — CLIENTES (admin only)
    # ═══════════════════════════════════════════════════════════════════════════
    elif page == "🏢 Clientes":
        st.title("🏢 Gerenciamento de Clientes")

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
                        
                    if cc3.button("🗑 Excluir", key=f"del_cli_{c}"):
                        delete_client(c)
                        st.rerun()
                        
                    if st.session_state.get(f"edit_cli_{c}", False):
                        rc1, rc2 = st.columns([6, 2])
                        novo_nome = rc1.text_input("Novo nome para o cliente:", value=c, key=f"new_name_{c}")
                        if rc2.button("Salvar alteração", key=f"save_ren_{c}"):
                            if novo_nome.strip() and novo_nome.strip() != c:
                                rename_client(c, novo_nome.strip())
                                st.rerun()
                st.markdown("---")

    # ═══════════════════════════════════════════════════════════════════════════
    #  PAGE 4 — USUÁRIOS  (admin only)
    # ═══════════════════════════════════════════════════════════════════════════
    elif page == "👥 Usuários":
        st.title("👥 Gerenciamento de Usuários")

        if role not in ["admin", "editor"]:
            st.warning("🔒 Acesso negado.")
            return

        # ── Criar novo usuário ────────────────────────────────────────────────
        with st.expander("➕ Criar novo usuário", expanded=False):
            nu1, nu2, nu3 = st.columns(3)
            new_uname = nu1.text_input("Usuário", key="nu_name")
            new_pw    = nu2.text_input("Senha",   key="nu_pw",   type="password")
            new_role  = nu3.selectbox("Perfil",   ["viewer", "editor", "admin"], key="nu_role")
            if st.button("Criar usuário", type="primary", key="nu_create"):
                if new_uname.strip() and new_pw.strip():
                    try:
                        add_user(new_uname.strip(), new_pw.strip(), new_role)
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

            with st.expander(f"{'🔑' if urole == 'admin' else '👤'} **{uname}**  ·  `{urole.upper()}`", expanded=False):
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
                    bc1, bc2 = st.columns(2)
                    if bc1.button("💾 Salvar", key=f"eu_save_{uname}"):
                        update_user(
                            uname,
                            new_password=new_pw_val.strip() or None,
                            new_role=new_role_sel if not is_self else None,
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


if __name__ == "__main__":
    main()
