import json

import streamlit as st

from auth import (
    get_campaigns,
    get_vehicles,
    get_ingestion_timestamps,
    save_ingestion,
)
from data_processor import (
    PLAN_FIELDS,
    ASSET_FIELDS,
    TAXONOMY_JOIN_FIELDS,
    apply_mapping,
    normalize_dates,
    aggregate_assets,
    fuzzy_merge_taxonomy,
    merge_taxonomy,
    compute_veiculacao_status,
    fuzzy_taxonomy_report,
)
from modules.shared import _page_header, _export_buttons
from modules.mapper import mapper_ui
from modules.wizard import (
    _duplicate_vehicle_ui,
    _step_bar,
    _step_campaign,
    _step_vehicle,
)


def render(username: str, role: str) -> None:
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

                def _reorder(df) -> "pd.DataFrame":
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
                        _export_buttons(fuzzy_df, "sugestoes_fuzzy", "exp_fuzzy")
