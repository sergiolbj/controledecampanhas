import pandas as pd
import streamlit as st

from auth import get_audit_log
from modules.shared import _page_header, _export_buttons


def render(username: str, role: str) -> None:
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
