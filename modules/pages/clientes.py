import streamlit as st

from auth import (
    get_clients,
    get_campaigns,
    add_client,
    rename_client,
)
from modules.shared import _page_header
from modules.dialogs import _dlg_del_cli


def render(username: str, role: str) -> None:
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
                    st.toast(f"Cliente **{new_cli.strip()}** adicionado.", icon="✅")
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
                    st.session_state.pop(f"edit_cli_{c}", None)
                    _dlg_del_cli(c, qtd)

                if st.session_state.get(f"edit_cli_{c}", False):
                    rc1, rc2 = st.columns([6, 2])
                    novo_nome = rc1.text_input("Novo nome:", value=c, key=f"new_name_{c}")
                    if rc2.button("Salvar", type="primary", key=f"save_ren_{c}"):
                        if novo_nome.strip() and novo_nome.strip() != c:
                            rename_client(c, novo_nome.strip())
                            st.toast(f"Cliente renomeado para **{novo_nome.strip()}**", icon="✅")
                            st.rerun()
            st.markdown("---")
