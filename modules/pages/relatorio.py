from datetime import datetime

import streamlit as st

from modules.shared import _page_header


def render(username: str, role: str) -> None:
    import streamlit.components.v1 as _stc
    _page_header("📄", "Relatório de Campanhas", "Gere e exporte o relatório consolidado")

    if st.button("🔄 Gerar relatório agora", type="primary", key="rpt_generate"):
        st.session_state.pop("_rpt_html", None)

    if "_rpt_html" not in st.session_state:
        with st.spinner("Gerando relatório…"):
            try:
                import sys as _sys, os as _os
                # Insert the project root (two levels up from modules/pages/)
                _root = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
                if _root not in _sys.path:
                    _sys.path.insert(0, _root)
                from report import gather_plan_data, deduplicate, compute_status, build_html
                _raw, _no_data = gather_plan_data()
                if not _raw.empty:
                    _raw = deduplicate(_raw)
                    _df_rpt = compute_status(_raw)
                else:
                    _df_rpt = _raw
                st.session_state["_rpt_html"] = build_html(_df_rpt, _no_data)
            except Exception as _rpt_err:
                st.error(f"Erro ao gerar relatório: {_rpt_err}")

    _html_rpt = st.session_state.get("_rpt_html")
    if _html_rpt:
        st.download_button(
            "⬇️ Baixar HTML",
            _html_rpt.encode("utf-8"),
            f"relatorio_{datetime.now().strftime('%Y%m%d_%H%M')}.html",
            "text/html",
            key="rpt_download",
        )
        _stc.html(_html_rpt, height=800, scrolling=True)
