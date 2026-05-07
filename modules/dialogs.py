import streamlit as st

from auth import (
    delete_campaign,
    log_audit,
    clear_campaign_data,
    delete_vehicle,
    delete_client,
    restore_ingestion_from_log,
)


# ── Modal dialogs (exclusões críticas) ────────────────────────────────────────
@st.dialog("🗑 Excluir campanha")
def _dlg_del_camp(cid: int, cname: str, n_vehs: int, _username: str) -> None:
    st.error(
        f"Excluir **{cname}** e todos os seus **{n_vehs} veículo(s)**?  \n"
        "Todo o plano e assets serão perdidos. Esta ação **não pode ser desfeita**."
    )
    c1, c2 = st.columns(2)
    if c1.button("Sim, excluir tudo", type="primary", key="dlg_del_camp_yes"):
        delete_campaign(cid)
        log_audit(_username, "excluir", "campanha", cname, f"{n_vehs} veículo(s) removidos")
        st.toast(f"Campanha **{cname}** excluída.", icon="🗑")
        st.rerun()
    if c2.button("Cancelar", key="dlg_del_camp_no"):
        st.rerun()


@st.dialog("🧹 Limpar dados da campanha")
def _dlg_clear_camp(cid: int, cname: str, n_vehs: int) -> None:
    st.warning(
        f"Isso apagará o **plano e os assets** de todos os **{n_vehs} veículo(s)** de **{cname}**.  \n"
        "O histórico (log) será mantido. Esta ação **não pode ser desfeita**."
    )
    c1, c2 = st.columns(2)
    if c1.button("Sim, limpar dados", type="primary", key="dlg_clear_camp_yes"):
        n = clear_campaign_data(cid)
        st.toast(f"{n} registro(s) removido(s) de **{cname}**.", icon="🧹")
        st.rerun()
    if c2.button("Cancelar", key="dlg_clear_camp_no"):
        st.rerun()


@st.dialog("🗑 Excluir veículo")
def _dlg_del_veh(vid: int, vname: str) -> None:
    st.warning(f"Excluir o veículo **{vname}** e todos os seus dados?")
    c1, c2 = st.columns(2)
    if c1.button("Sim, excluir", type="primary", key="dlg_del_veh_yes"):
        delete_vehicle(vid)
        st.toast(f"Veículo **{vname}** excluído.", icon="🗑")
        st.rerun()
    if c2.button("Cancelar", key="dlg_del_veh_no"):
        st.rerun()


@st.dialog("🗑 Excluir cliente")
def _dlg_del_cli(name: str, n_camps: int) -> None:
    st.warning(
        f"Excluir **{name}**? Isso desvincula **{n_camps} campanha(s)**. "
        "Esta ação **não pode ser desfeita**."
    )
    c1, c2 = st.columns(2)
    if c1.button("Sim, excluir", type="primary", key="dlg_del_cli_yes"):
        delete_client(name)
        st.toast(f"Cliente **{name}** excluído.", icon="🗑")
        st.rerun()
    if c2.button("Cancelar", key="dlg_del_cli_no"):
        st.rerun()


@st.dialog("↩ Restaurar versão")
def _dlg_restore(entry: dict) -> None:
    _ts_str = entry["ts"].strftime("%d/%m/%Y %H:%M") if entry["ts"] and hasattr(entry["ts"], "strftime") else str(entry["ts"] or "")[:16]
    _dtype_lbl = "Plano" if entry["data_type"] == "plan" else "Assets"
    st.info(
        f"Restaurar versão de **{_ts_str}** ({_dtype_lbl}, {entry['row_count']:,} linhas)?  \n"
        "Os dados atuais serão substituídos por esta versão."
    )
    c1, c2 = st.columns(2)
    if c1.button("Restaurar", type="primary", key="dlg_restore_yes"):
        try:
            restore_ingestion_from_log(entry["id"])
            st.toast("Versão restaurada com sucesso!", icon="✅")
            st.rerun()
        except Exception as _exc:
            st.error(str(_exc))
    if c2.button("Cancelar", key="dlg_restore_no"):
        st.rerun()
