import json

import streamlit as st

from auth import (
    get_campaigns,
    get_vehicles,
    get_clients,
    create_campaign,
    create_vehicle,
    update_campaign_client,
    save_user_state,
    load_ingestion,
    save_ingestion,
)
from data_processor import (
    read_file,
    apply_mapping,
    normalize_dates,
)


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

                    st.toast(
                        f"Cópia criada: **{resolved_camp_name} › {dst_veh_name.strip()}**",
                        icon="✅",
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
