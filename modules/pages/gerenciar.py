import streamlit as st
import pandas as pd

from auth import (
    get_campaigns,
    get_vehicles,
    create_campaign,
    create_vehicle,
    rename_campaign,
    rename_vehicle,
    archive_campaign,
    get_pending_vehicles,
    get_mapping_coverage,
    get_ingestion_timestamps,
    get_ingestion_log,
    get_vehicle_notes,
    add_vehicle_note,
    delete_vehicle_note,
    get_alert_configs,
    save_alert_config,
    update_alert_config,
    delete_alert_config,
    log_audit,
)
from modules.shared import _page_header, _export_buttons
from modules.dialogs import _dlg_del_camp, _dlg_clear_camp, _dlg_del_veh, _dlg_restore


def render(username: str, role: str) -> None:
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
                st.toast(
                    f"✅ {_created} campanha(s) criada(s), {_skipped} já existia(m). "
                    f"{_vehs_created} veículo(s) adicionado(s).",
                    icon="✅",
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
            _export_buttons(_cov_df, "cobertura_mapeamento", "exp_cov")
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
                            st.toast(f"Renomeada para **{new_cname.strip()}**", icon="✅")
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
                    st.toast(f"{'Arquivada' if not _is_archived else 'Desarquivada'}: **{cname}**", icon="🗄")
                    st.rerun()

                # ── Excluir campanha ───────────────────────────────────
                if st.button("🗑 Excluir campanha", key=f"del_camp_btn_{cid}"):
                    _dlg_del_camp(cid, cname, len(vehs), username)

                # ── Limpar dados da campanha (item 21) ────────────────
                if st.button("🧹 Limpar todos os dados", key=f"clear_data_btn_{cid}",
                             help="Remove plano e assets de todos os veículos desta campanha"):
                    _dlg_clear_camp(cid, cname, len(vehs))

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
                                    st.toast(f"Veículo renomeado para **{new_vname.strip()}**", icon="✅")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Erro: {e}")
                        if vc3.button("🗑", key=f"del_veh_btn_{vid}", help="Excluir veículo"):
                            _dlg_del_veh(vid, vname)

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
                                        _dlg_restore(_e)
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
                                st.toast("Alerta salvo!", icon="🔔")
                                st.rerun()
                            if _ae and st.button("🗑 Remover", key=f"al_del_{cid}_{_atype}"):
                                delete_alert_config(_ae["id"])
                                st.rerun()
                            st.markdown("---")
