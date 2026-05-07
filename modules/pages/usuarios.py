import pandas as pd
import streamlit as st

from auth import (
    get_users,
    get_clients,
    add_user,
    update_user,
    delete_user,
    get_user_clients,
    set_user_clients,
    get_report_recipients,
    add_report_recipient,
    toggle_report_recipient,
    delete_report_recipient,
    get_system_config,
    set_system_config,
    get_login_history,
)
from modules.shared import _page_header, _export_buttons


def render(username: str, role: str) -> None:
    _page_header("👥", "Usuários", "Gerencie acessos, perfis e destinatários de relatório")

    if role not in ["admin", "editor"]:
        st.warning("🔒 Acesso negado.")
        return

    # ── Criar novo usuário ────────────────────────────────────────────────
    with st.expander("➕ Criar novo usuário", expanded=False):
        nu1, nu2, nu3 = st.columns(3)
        new_uname = nu1.text_input("Usuário", key="nu_name")
        new_pw    = nu2.text_input("Senha",   key="nu_pw",   type="password")
        new_role  = nu3.selectbox("Perfil",   ["viewer", "editor", "admin"], key="nu_role")
        new_email = st.text_input("E-mail (para receber relatórios)", key="nu_email", placeholder="usuario@exemplo.com")
        if st.button("Criar usuário", type="primary", key="nu_create"):
            if new_uname.strip() and new_pw.strip():
                try:
                    add_user(new_uname.strip(), new_pw.strip(), new_role, email=new_email.strip())
                    st.toast(f"Usuário **{new_uname}** criado.", icon="✅")
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

        _uemail = u.get("email", "")
        _email_tag = f"  ·  ✉️ {_uemail}" if _uemail else ""
        with st.expander(f"{'🔑' if urole == 'admin' else '👤'} **{uname}**  ·  `{urole.upper()}`{_email_tag}", expanded=False):
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
                new_email_val = st.text_input(
                    "E-mail", value=_uemail, key=f"eu_email_{uname}",
                    placeholder="usuario@exemplo.com",
                )
                bc1, bc2 = st.columns(2)
                if bc1.button("💾 Salvar", type="primary", key=f"eu_save_{uname}"):
                    update_user(
                        uname,
                        new_password=new_pw_val.strip() or None,
                        new_role=new_role_sel if not is_self else None,
                        new_email=new_email_val.strip(),
                    )
                    st.toast(f"Usuário **{uname}** atualizado.", icon="✅")
                    st.rerun()
                if bc2.button("🗑 Excluir", key=f"eu_del_{uname}", disabled=is_self,
                              type="secondary"):
                    delete_user(uname)
                    st.toast(f"Usuário **{uname}** removido.", icon="🗑")
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
                            st.toast("Acesso atualizado.", icon="✅")
                            st.rerun()
                    else:
                        st.info("Nenhum cliente cadastrado no Gerenciador de Clientes.")
                else:
                    st.caption("Admins visualizam todas as campanhas independente do cliente.")

    # ── Destinatários do relatório diário ─────────────────────────────────
    if role == "admin":
        st.divider()
        st.subheader("📧 Destinatários do Relatório Diário")
        st.caption(
            "Configure quais e-mails recebem o relatório por cliente. "
            "Usuários com e-mail cadastrado e cliente associado também recebem automaticamente."
        )

        _rr_clients = get_clients()
        if not _rr_clients:
            st.info("Nenhum cliente cadastrado.")
        else:
            _rr_sel_client = st.selectbox(
                "Filtrar por cliente", ["— todos —"] + _rr_clients, key="rr_client_filter"
            )
            _rr_list = get_report_recipients(
                None if _rr_sel_client == "— todos —" else _rr_sel_client
            )

            if _rr_list:
                for _rr in _rr_list:
                    _rc1, _rc2, _rc3 = st.columns([4, 1, 1])
                    _rc1.write(f"**{_rr['email']}**  ·  `{_rr['client_name']}`")
                    _active_label = "✅ Ativo" if _rr["active"] else "⏸ Pausado"
                    if _rc2.button(_active_label, key=f"rr_tog_{_rr['id']}"):
                        toggle_report_recipient(_rr["id"], not _rr["active"])
                        st.rerun()
                    if _rc3.button("🗑", key=f"rr_del_{_rr['id']}", help="Remover destinatário"):
                        delete_report_recipient(_rr["id"])
                        st.rerun()
            else:
                st.caption("Nenhum destinatário cadastrado para este filtro.")

            st.markdown("**Adicionar destinatário**")
            _ra1, _ra2, _ra3 = st.columns([2, 3, 1])
            _rr_new_client = _ra1.selectbox("Cliente", _rr_clients, key="rr_new_client")
            _rr_new_email  = _ra2.text_input("E-mail", key="rr_new_email", placeholder="destinatario@exemplo.com")
            _ra3.write(""); _ra3.write("")
            if _ra3.button("➕ Add", type="primary", key="rr_add"):
                if _rr_new_email.strip():
                    if "@" not in _rr_new_email:
                        st.error("E-mail inválido. Use o formato usuario@dominio.com.")
                    else:
                        add_report_recipient(_rr_new_client, _rr_new_email.strip())
                        st.toast(f"Destinatário **{_rr_new_email}** adicionado.", icon="✅")
                        st.rerun()
                else:
                    st.warning("Informe um e-mail.")

    # ── Item 42: Timeout de sessão por inatividade ────────────────────────
    if role == "admin":
        st.divider()
        st.subheader("🔐 Segurança da Sessão")
        _cur_timeout = int(get_system_config("session_timeout_hours", "8"))
        _new_timeout = st.number_input(
            "Tempo máximo de inatividade (horas)",
            min_value=1, max_value=168, value=_cur_timeout, step=1,
            help="Sessões sem atividade por mais deste tempo serão encerradas automaticamente.",
            key="session_timeout_input",
        )
        if st.button("💾 Salvar timeout", type="primary", key="save_timeout"):
            set_system_config("session_timeout_hours", str(_new_timeout))
            st.toast(f"Timeout atualizado para {_new_timeout}h.", icon="🔐")

    # ── Item 43: Histórico de logins por usuário ──────────────────────────
    if role == "admin":
        st.divider()
        st.subheader("🔑 Histórico de Logins Recentes")
        _lh_all = get_login_history(limit=100)
        if _lh_all:
            _lh_df = pd.DataFrame(_lh_all)
            _lh_df["ts"] = pd.to_datetime(_lh_df["ts"]).dt.strftime("%d/%m/%Y %H:%M:%S")
            _lh_df["resultado"] = _lh_df["success"].map({True: "✅ Sucesso", False: "❌ Falha"})
            _lh_display = _lh_df[["ts", "username", "resultado"]].rename(columns={
                "ts": "Data/Hora", "username": "Usuário", "resultado": "Resultado"
            })
            st.dataframe(_lh_display, use_container_width=True, hide_index=True, height=300)
            _export_buttons(_lh_display, "historico_logins", "exp_logins")
        else:
            st.caption("Nenhum login registrado ainda.")
