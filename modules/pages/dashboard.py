import json

import pandas as pd
import plotly.express as px
import streamlit as st

from auth import (
    get_campaigns,
    get_vehicles,
    load_ingestion,
    save_ingestion,
)
from data_processor import (
    FIELD_LABELS,
    TAXONOMY_JOIN_FIELDS,
    aggregate_assets,
    apply_mapping,
    compute_veiculacao_status,
    fuzzy_merge_taxonomy,
    normalize_dates,
    read_file,
)
from modules.shared import _page_header, _export_buttons
from modules.mapper import gantt_chart


def render(username: str, role: str) -> None:
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
                st.toast("Sincronizado com sucesso!", icon="🔄")
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
                _rows_df = pd.DataFrame(_rows)
                st.dataframe(_rows_df, use_container_width=True, hide_index=True)
                st.caption(f"Período A: **{len(_fa):,}** linhas · Período B: **{len(_fb):,}** linhas")
                _export_buttons(_rows_df, "comparacao_periodos", "exp_periods")

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
            _export_buttons(_agg, "orcamento_gasto", "exp_budget")

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
