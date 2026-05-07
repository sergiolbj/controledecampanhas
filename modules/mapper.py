import json

import pandas as pd
import plotly.express as px
import streamlit as st

from auth import get_db, get_clients
from data_processor import (
    FIELD_LABELS,
    get_sheets,
    get_sheets_from_url,
    apply_mapping,
    normalize_dates,
    read_file,
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
    load_templates.clear()


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

        # ── Templates (carregar e salvar no mesmo expander) ───────────────
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
                        st.toast(f"Template **{tpl_name}** salvo para **{tpl_client}**!", icon="💾")
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
