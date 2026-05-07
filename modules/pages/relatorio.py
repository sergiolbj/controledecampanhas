import json
from datetime import datetime

import streamlit as st
import streamlit.components.v1 as _stc

from modules.shared import _page_header

_PDF_BTN_HTML = """
<script src="https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.10.1/html2pdf.bundle.min.js"></script>
<style>
  body{{margin:0;padding:0}}
  #pdf-dl{{
    display:inline-flex;align-items:center;gap:6px;
    background:#f0f2f6;color:#31333f;border:1px solid #d0d3dc;
    border-radius:4px;padding:5px 14px;font-size:14px;font-weight:400;
    font-family:sans-serif;cursor:pointer;white-space:nowrap;
    transition:border-color .15s,background .15s;
  }}
  #pdf-dl:hover{{background:#e8eaf0;border-color:#b0b3bc}}
</style>
<button id="pdf-dl">⬇️ Baixar PDF</button>
<script>
document.getElementById('pdf-dl').onclick = function() {{
  var btn = this;
  btn.textContent = '⏳ Gerando PDF…';
  btn.disabled = true;
  var htmlContent = {html_json};
  var parser = new DOMParser();
  var doc = parser.parseFromString(htmlContent, 'text/html');
  // Remove the floating pdf button from the standalone html if present
  var fb = doc.getElementById('pdf-btn');
  if (fb) fb.remove();
  html2pdf().set({{
    margin: 10,
    filename: '{filename}',
    image: {{type:'jpeg', quality:0.95}},
    html2canvas: {{scale:2, useCORS:true, logging:false}},
    jsPDF: {{unit:'mm', format:'a4', orientation:'portrait'}}
  }}).from(doc.getElementById('report-wrap') || doc.body).save()
  .then(function(){{
    btn.textContent = '⬇️ Baixar PDF';
    btn.disabled = false;
  }});
}};
</script>
"""


def render(username: str, role: str) -> None:
    _page_header("📄", "Relatório de Campanhas", "Gere e exporte o relatório consolidado")

    if st.button("🔄 Gerar relatório agora", type="primary", key="rpt_generate"):
        st.session_state.pop("_rpt_html", None)

    if "_rpt_html" not in st.session_state:
        with st.spinner("Gerando relatório…"):
            try:
                import sys as _sys, os as _os
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
        _ts = datetime.now().strftime("%Y%m%d_%H%M")
        _pdf_name = f"relatorio_{_ts}.pdf"

        _dl_col, _pdf_col, _spacer = st.columns([1, 1, 4])
        with _dl_col:
            st.download_button(
                "⬇️ Baixar HTML",
                _html_rpt.encode("utf-8"),
                f"relatorio_{_ts}.html",
                "text/html",
                key="rpt_download",
                use_container_width=True,
            )
        with _pdf_col:
            _btn_html = _PDF_BTN_HTML.format(
                html_json=json.dumps(_html_rpt),
                filename=_pdf_name,
            )
            _stc.html(_btn_html, height=40)

        _stc.html(_html_rpt, height=900, scrolling=True)
