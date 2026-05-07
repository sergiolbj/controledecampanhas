import streamlit as st
import pandas as pd
import plotly.express as px

from auth import (
    get_campaigns,
    get_vehicles,
    create_campaign,
    create_vehicle,
    load_campaign_sheets_config,
    save_campaign_sheets_config,
    log_audit,
)
from data_processor import (
    get_sheets_from_url,
    read_file,
    read_campaign_sheet,
)
from modules.shared import _page_header, _export_buttons


def render(username: str, role: str) -> None:
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
                    st.toast("Configuração salva! Recarregando dados…", icon="💾")
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
                                st.toast(f"{_camp_name}: {_veh_ok} veículo(s) criado(s).", icon="✅")
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
