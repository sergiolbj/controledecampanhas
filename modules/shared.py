import streamlit as st
import pandas as pd


# ── Page header helper ────────────────────────────────────────────────────────
def _page_header(icon: str, title: str, subtitle: str = "") -> None:
    sub_html = f'<p style="margin:4px 0 0;font-size:.875rem;color:var(--t2)">{subtitle}</p>' if subtitle else ""
    st.markdown(f"""
    <div style="display:flex;align-items:center;gap:14px;margin-bottom:1.75rem;
                padding-bottom:1.25rem;border-bottom:1px solid var(--bd)">
      <div style="width:44px;height:44px;background:linear-gradient(135deg,#2563eb,#1d4ed8);
                  border-radius:12px;display:flex;align-items:center;justify-content:center;
                  font-size:20px;flex-shrink:0;box-shadow:0 2px 8px rgba(37,99,235,.3)">{icon}</div>
      <div>
        <h1 style="margin:0;font-size:1.5rem;font-weight:700;color:var(--t1);
                   letter-spacing:-.02em;line-height:1.2">{title}</h1>
        {sub_html}
      </div>
    </div>
    """, unsafe_allow_html=True)


# ── Export helper ─────────────────────────────────────────────────────────────
def _export_buttons(df: pd.DataFrame, base_name: str, key: str) -> None:
    """Renderiza botões de download CSV e Excel lado a lado."""
    import io as _io
    ec1, ec2 = st.columns(2)
    ec1.download_button(
        "⬇️ Exportar CSV",
        df.to_csv(index=False).encode("utf-8"),
        f"{base_name}.csv", "text/csv",
        key=f"{key}_csv",
    )
    _buf = _io.BytesIO()
    with pd.ExcelWriter(_buf, engine="openpyxl") as _w:
        df.to_excel(_w, index=False, sheet_name="Dados")
    ec2.download_button(
        "⬇️ Exportar Excel",
        _buf.getvalue(),
        f"{base_name}.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=f"{key}_xlsx",
    )
