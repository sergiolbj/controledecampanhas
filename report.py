#!/usr/bin/env python3
"""
Daily AdOps status report.

Run via GitHub Actions (see .github/workflows/daily_report.yml).
Required env vars: DATABASE_URL, SMTP_HOST, SMTP_USER, SMTP_PASS, REPORT_TO
Optional:         SMTP_PORT (default 587), REPORT_FROM (defaults to SMTP_USER)
"""

from __future__ import annotations

import io
import json
import os
import pickle
import smtplib
import sys
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import pandas as pd
import psycopg2

# data_processor lives next to this file (same repo)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_processor import read_file, apply_mapping, normalize_dates  # noqa: E402

# ── DB helpers ────────────────────────────────────────────────────────────────

DB_URL = os.environ["DATABASE_URL"]


def _db():
    return psycopg2.connect(DB_URL)


def get_all_campaigns() -> list[dict]:
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, name, COALESCE(client_name,'') "
                "FROM campaigns ORDER BY client_name, name"
            )
            return [{"id": r[0], "name": r[1], "client": r[2]} for r in cur.fetchall()]


def get_vehicles(campaign_id: int) -> list[dict]:
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, name FROM vehicles WHERE campaign_id=%s ORDER BY name",
                (campaign_id,),
            )
            return [{"id": r[0], "name": r[1]} for r in cur.fetchall()]


def _fetch_from_sheets(cfg: dict, mapping: dict) -> pd.DataFrame | None:
    """Re-fetch plan from Google Sheets using saved config + mapping."""
    url = cfg.get("url")
    if not url:
        return None
    try:
        df = read_file(
            "url",
            url=url,
            sheet_name=cfg.get("sheet", 0),
            header_row=cfg.get("header_row", 0),
        )
        if df is None or df.empty:
            return None

        veh_col    = cfg.get("veh_col", "(não usar)")
        veh_filter = cfg.get("veh_filter", "")
        if veh_col != "(não usar)" and veh_filter.strip():
            mask = (
                df[veh_col].astype(str).str.strip().str.lower()
                == veh_filter.strip().lower()
            )
            df = df[mask].copy()
        if veh_col != "(não usar)" and veh_col in df.columns:
            df = df.drop(columns=[veh_col])

        active = {k: v for k, v in mapping.items() if v != "(não mapear)"}
        df = normalize_dates(apply_mapping(df, active), ["start_date", "end_date"])
        return df if not df.empty else None
    except Exception as exc:
        print(f"      [sheets fallback] erro: {exc}")
        return None


_PARQUET_MAGIC = b"\x00PQT\x00"


def load_plan(campaign_id: int, vehicle_id: int) -> pd.DataFrame | None:
    """Load plan from DB cache; falls back to Google Sheets if cache is stale/missing."""
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT data_blob, mapping_json, config_json FROM ingestion_cache "
                "WHERE campaign_id=%s AND vehicle_id=%s AND data_type='plan'",
                (campaign_id, vehicle_id),
            )
            row = cur.fetchone()

    if not row:
        return None  # no entry at all — vehicle was never saved

    mapping = json.loads(row[1]) if row[1] else {}
    cfg     = json.loads(row[2]) if row[2] else {}

    # ── Try the cached blob (parquet or legacy pickle) ────────────────────────
    try:
        blob = row[0]
        if isinstance(blob, memoryview):
            blob = blob.tobytes()

        if blob.startswith(_PARQUET_MAGIC):
            df = pd.read_parquet(io.BytesIO(blob[len(_PARQUET_MAGIC):]), engine="pyarrow")
        else:
            df = pickle.loads(blob)  # legacy pickle blobs

        if isinstance(df, pd.DataFrame) and not df.empty:
            return df
        print("      [cache] blob vazio ou não-DataFrame")
    except Exception as exc:
        print(f"      [cache] falha ao carregar blob: {type(exc).__name__}: {exc}")

    # ── Fallback: re-fetch from Google Sheets ─────────────────────────────────
    src = cfg.get("src", "")
    if "Sheets" in src or "Office" in src:
        print("      [sheets fallback] tentando re-buscar do Sheets...")
        return _fetch_from_sheets(cfg, mapping)

    return None


# ── Data assembly ─────────────────────────────────────────────────────────────

def gather_plan_data() -> tuple[pd.DataFrame, list[dict]]:
    """Return (all_plan_rows, no_data_items).

    no_data_items: list of {campaign, vehicle} that have no plan in the DB.
    """
    camps = get_all_campaigns()
    print(f"[diagnóstico] campanhas encontradas: {len(camps)}")

    frames: list[pd.DataFrame] = []
    no_data: list[dict] = []

    for camp in camps:
        vehs = get_vehicles(camp["id"])
        print(f"  campanha '{camp['name']}' — {len(vehs)} veículo(s)")
        for v in vehs:
            df = load_plan(camp["id"], v["id"])
            if df is None or df.empty:
                print(f"    [{v['name']}] sem plano no banco")
                no_data.append({"sys_client": camp["client"],
                                "sys_campaign": camp["name"],
                                "sys_vehicle": v["name"]})
                continue
            print(f"    [{v['name']}] {len(df)} linhas | colunas: {list(df.columns)[:10]}")
            df = df.copy()
            df["sys_campaign"] = camp["name"]
            df["sys_vehicle"]  = v["name"]
            df["sys_client"]   = camp["client"]
            frames.append(df)

    if not frames:
        return pd.DataFrame(), no_data

    result = pd.concat(frames, ignore_index=True)
    print(f"[diagnóstico] total de linhas: {len(result)}")
    return result, no_data


# Common alternative names for date columns (user may have mapped differently)
_DATE_ALIASES = {
    "start_date": ["start_date", "data_inicio", "data inicio", "inicio", "data_de_inicio",
                   "start", "flight_start", "data_começo"],
    "end_date":   ["end_date",   "data_fim",    "data fim",    "fim",    "data_de_fim",
                   "end",   "flight_end",   "data_termino", "data_encerramento"],
}


def _find_date_col(df: pd.DataFrame, canonical: str) -> str | None:
    """Return the actual column name for a canonical date field, or None."""
    cols_lower = {c.lower().strip().replace(" ", "_"): c for c in df.columns}
    for alias in _DATE_ALIASES[canonical]:
        if alias in cols_lower:
            return cols_lower[alias]
    return None


def compute_status(df: pd.DataFrame) -> pd.DataFrame:
    """Classify each creative row using plan start/end dates only."""
    df = df.copy()
    today = pd.Timestamp.now().normalize()

    for canonical in ("start_date", "end_date"):
        actual = _find_date_col(df, canonical)
        if actual and actual != canonical:
            # rename alias to canonical so the rest of the code is uniform
            df = df.rename(columns={actual: canonical})
            print(f"[diagnóstico] coluna '{actual}' mapeada como '{canonical}'")

    for col in ("start_date", "end_date"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
            valid = df[col].notna().sum()
            print(f"[diagnóstico] {col}: {valid}/{len(df)} valores válidos")
        else:
            df[col] = pd.NaT
            print(f"[diagnóstico] {col}: coluna ausente — atribuída NaT")

    def _row(r):
        ini, fim = r["start_date"], r["end_date"]
        no_ini, no_fim = pd.isna(ini), pd.isna(fim)

        if no_ini and no_fim:
            return "⏳ Sem datas", None

        if not no_fim and fim < today:
            return "🏁 Encerrada", int((fim - today).days)   # negative

        if not no_ini and ini > today:
            return "📅 Aguardando início", int((ini - today).days)  # positive

        if not no_fim:
            return "▶️ Em veiculação", int((fim - today).days)  # days remaining

        return "▶️ Em veiculação", None

    info = df.apply(_row, axis=1, result_type="expand")
    df["_status"] = info[0]
    df["_dias"]   = info[1]
    return df


def deduplicate(df: pd.DataFrame) -> pd.DataFrame:
    """Keep one row per creative (plan may have repeated rows from shared sheets)."""
    key = [c for c in ("sys_campaign", "sys_vehicle", "ad_name") if c in df.columns]
    if not key:
        return df
    # Keep the row with the latest end_date when duplicates exist
    sort_cols = [c for c in ("end_date", "start_date") if c in df.columns]
    if sort_cols:
        df = df.sort_values(sort_cols, ascending=False)
    return df.drop_duplicates(subset=key, keep="first").reset_index(drop=True)


# ── HTML email builder ────────────────────────────────────────────────────────

_PALETTE = {
    "bg":       "#f0f4f8",
    "card":     "#ffffff",
    "header":   "#1e293b",
    "accent":   "#3b82f6",
    "muted":    "#64748b",
    "border":   "#e2e8f0",
    "active":   "#16a34a",
    "warn":     "#d97706",
    "ended":    "#64748b",
    "upcoming": "#2563eb",
}

_SECTION_COLORS = {
    "active":   ("#dcfce7", "#166534"),
    "ending":   ("#fef3c7", "#92400e"),
    "upcoming": ("#dbeafe", "#1e40af"),
    "ended":    ("#f1f5f9", "#475569"),
}


def _fmt_date(val) -> str:
    try:
        return pd.Timestamp(val).strftime("%d/%m/%y")
    except Exception:
        return "—"


def _pill(text: str, bg: str, fg: str) -> str:
    return (
        f'<span style="background:{bg};color:{fg};padding:2px 8px;'
        f'border-radius:12px;font-size:11px;font-weight:600">{text}</span>'
    )


def _summary_pill(label: str, count: int, color: str) -> str:
    return (
        f'<div style="text-align:center;background:{color};border-radius:8px;'
        f'padding:12px 16px;min-width:110px">'
        f'<div style="font-size:26px;font-weight:700;color:#1e293b">{count}</div>'
        f'<div style="font-size:11px;color:#475569;margin-top:2px">{label}</div>'
        f'</div>'
    )


def _table(rows: pd.DataFrame, cols: list[tuple[str, str]], days_col: bool = False) -> str:
    available = [(c, lbl) for c, lbl in cols if c in rows.columns]
    if not available:
        return "<p style='color:#64748b;font-size:13px'>Sem dados.</p>"

    header_cells = "".join(
        f'<th style="text-align:left;padding:6px 10px;font-size:12px;'
        f'color:#64748b;font-weight:600;border-bottom:1px solid #e2e8f0">{lbl}</th>'
        for _, lbl in available
    )
    if days_col:
        header_cells += (
            '<th style="text-align:right;padding:6px 10px;font-size:12px;'
            'color:#64748b;font-weight:600;border-bottom:1px solid #e2e8f0">Dias</th>'
        )

    body = ""
    for i, (_, row) in enumerate(rows.iterrows()):
        bg = "#f8fafc" if i % 2 == 0 else "#ffffff"
        cells = ""
        for col, _ in available:
            val = row.get(col, "")
            if col in ("start_date", "end_date"):
                val = _fmt_date(val)
            else:
                val = str(val) if pd.notna(val) else "—"
            cells += (
                f'<td style="padding:6px 10px;font-size:12px;'
                f'color:#1e293b;border-bottom:1px solid #f1f5f9">{val}</td>'
            )
        if days_col:
            d = row.get("_dias")
            if d is None or pd.isna(d):
                d_str = "—"
            else:
                d = int(d)
                d_str = f"+{d}d" if d >= 0 else f"{d}d"
            cells += (
                f'<td style="padding:6px 10px;font-size:12px;text-align:right;'
                f'color:#64748b;border-bottom:1px solid #f1f5f9">{d_str}</td>'
            )
        body += f'<tr style="background:{bg}">{cells}</tr>'

    return (
        f'<table style="width:100%;border-collapse:collapse">'
        f'<thead><tr>{header_cells}</tr></thead>'
        f'<tbody>{body}</tbody>'
        f'</table>'
    )


def _section(title: str, subtitle: str, rows: pd.DataFrame,
             cols: list[tuple[str, str]], bg: str, fg: str,
             days_col: bool = False) -> str:
    count = len(rows)
    if count == 0:
        content = "<p style='color:#64748b;font-size:13px;margin:0'>Nenhum item.</p>"
    else:
        content = _table(rows, cols, days_col)

    return (
        f'<div style="margin:0 0 20px;border-radius:8px;overflow:hidden;'
        f'border:1px solid #e2e8f0">'
        f'<div style="background:{bg};padding:10px 16px;display:flex;'
        f'align-items:center;justify-content:space-between">'
        f'<div>'
        f'<span style="font-size:14px;font-weight:700;color:{fg}">{title}</span>'
        f'<span style="font-size:12px;color:{fg};opacity:.7;margin-left:8px">{subtitle}</span>'
        f'</div>'
        f'<span style="background:{fg};color:white;border-radius:12px;'
        f'padding:2px 10px;font-size:12px;font-weight:700">{count}</span>'
        f'</div>'
        f'<div style="padding:12px 16px;background:#fff">{content}</div>'
        f'</div>'
    )


PLAN_COLS = [
    ("sys_client",   "Cliente"),
    ("sys_campaign", "Campanha"),
    ("sys_vehicle",  "Veículo"),
    ("ad_name",      "Criativo"),
    ("format",       "Formato"),
    ("start_date",   "Início"),
    ("end_date",     "Fim"),
]


def _no_data_section(items: list[dict]) -> str:
    """Renders a warning section for vehicles with no plan in the DB."""
    if not items:
        return ""
    rows_html = ""
    for i, it in enumerate(items):
        bg = "#fff7ed" if i % 2 == 0 else "#fff"
        rows_html += (
            f'<tr style="background:{bg}">'
            f'<td style="padding:6px 10px;font-size:12px;color:#1e293b;border-bottom:1px solid #fef3c7">'
            f'{it.get("sys_client") or "—"}</td>'
            f'<td style="padding:6px 10px;font-size:12px;color:#1e293b;border-bottom:1px solid #fef3c7">'
            f'{it["sys_campaign"]}</td>'
            f'<td style="padding:6px 10px;font-size:12px;color:#1e293b;border-bottom:1px solid #fef3c7">'
            f'{it["sys_vehicle"]}</td>'
            f'</tr>'
        )
    table = (
        '<table style="width:100%;border-collapse:collapse">'
        '<thead><tr>'
        '<th style="text-align:left;padding:6px 10px;font-size:12px;color:#92400e;font-weight:600;border-bottom:1px solid #fde68a">Cliente</th>'
        '<th style="text-align:left;padding:6px 10px;font-size:12px;color:#92400e;font-weight:600;border-bottom:1px solid #fde68a">Campanha</th>'
        '<th style="text-align:left;padding:6px 10px;font-size:12px;color:#92400e;font-weight:600;border-bottom:1px solid #fde68a">Veículo</th>'
        f'</tr></thead><tbody>{rows_html}</tbody></table>'
    )
    return (
        f'<div style="margin:0 0 20px;border-radius:8px;overflow:hidden;border:1px solid #fde68a">'
        f'<div style="background:#fef3c7;padding:10px 16px;display:flex;align-items:center;justify-content:space-between">'
        f'<div><span style="font-size:14px;font-weight:700;color:#92400e">⚠️ Sem dados no banco</span>'
        f'<span style="font-size:12px;color:#92400e;opacity:.7;margin-left:8px">Mapeamento & Cruzamento pendente</span>'
        f'</div>'
        f'<span style="background:#92400e;color:white;border-radius:12px;padding:2px 10px;font-size:12px;font-weight:700">{len(items)}</span>'
        f'</div>'
        f'<div style="padding:12px 16px;background:#fffbeb">{table}</div>'
        f'</div>'
    )


def build_html(df: pd.DataFrame, no_data: list[dict] | None = None) -> str:
    today_str = datetime.now().strftime("%d/%m/%Y")

    if df.empty or "_status" not in df.columns:
        df = pd.DataFrame(columns=["_status", "_dias"])

    active   = df[df["_status"] == "▶️ Em veiculação"].copy()
    ending   = active[active["_dias"].notna() & (active["_dias"] <= 7)].copy()
    ending   = ending.sort_values("_dias")
    upcoming = df[(df["_status"] == "📅 Aguardando início") & (df["_dias"] <= 7)].copy()
    upcoming = upcoming.sort_values("_dias")
    # 30-day window for recently ended
    ended    = df[(df["_status"] == "🏁 Encerrada") & (df["_dias"] >= -30)].copy()
    ended    = ended.sort_values("_dias", ascending=False)

    n_active   = len(active)
    n_ending   = len(ending)
    n_upcoming = len(upcoming)
    n_ended    = len(ended)

    summary = (
        '<div style="display:flex;gap:12px;flex-wrap:wrap;justify-content:center;'
        'padding:16px 32px;background:#f8fafc;border-bottom:1px solid #e2e8f0">'
        + _summary_pill("Em veiculação", n_active, "#dcfce7")
        + _summary_pill("Encerrando (7d)", n_ending, "#fef3c7")
        + _summary_pill("Iniciando (7d)", n_upcoming, "#dbeafe")
        + _summary_pill("Encerrados (30d)", n_ended, "#f1f5f9")
        + '</div>'
    )

    sc = _SECTION_COLORS
    sections = (
        _section("▶️ Em veiculação agora", "criativos ativos",
                 active, PLAN_COLS, *sc["active"], days_col=True)
        + _section("⚠️ Encerrando nos próximos 7 dias", "requer atenção",
                   ending, PLAN_COLS, *sc["ending"], days_col=True)
        + _section("📅 Iniciando nos próximos 7 dias", "novos criativos",
                   upcoming, PLAN_COLS, *sc["upcoming"], days_col=True)
        + _section("🏁 Encerrados recentemente", "últimos 30 dias",
                   ended, PLAN_COLS, *sc["ended"], days_col=True)
        + _no_data_section(no_data or [])
    )

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:24px;background:#f0f4f8;font-family:Arial,Helvetica,sans-serif">
  <div style="max-width:740px;margin:0 auto;background:#fff;border-radius:10px;
               overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,.08)">

    <!-- Header -->
    <div style="background:#1e293b;padding:20px 32px">
      <h1 style="margin:0;color:#fff;font-size:18px">📊 Relatório Diário de Campanhas PPG</h1>
      <p style="margin:4px 0 0;color:#94a3b8;font-size:12px">{today_str}</p>
    </div>

    <!-- Summary -->
    {summary}

    <!-- Sections -->
    <div style="padding:20px 24px">
      {sections}
    </div>

    <!-- Footer -->
    <div style="background:#f8fafc;padding:12px 32px;border-top:1px solid #e2e8f0;
                text-align:center;color:#94a3b8;font-size:11px">
      Controle de Campanhas PPG · gerado automaticamente em {today_str}
    </div>
  </div>
</body>
</html>"""


# ── Email sender ──────────────────────────────────────────────────────────────

def send_email(html: str) -> None:
    host     = os.environ["SMTP_HOST"]
    port     = int(os.environ.get("SMTP_PORT", "587"))
    user     = os.environ["SMTP_USER"]
    password = os.environ["SMTP_PASS"]
    to       = os.environ["REPORT_TO"]
    from_    = os.environ.get("REPORT_FROM", user)

    today_str = datetime.now().strftime("%d/%m/%Y")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"📊 Relatório de Campanhas PPG — {today_str}"
    msg["From"]    = from_
    msg["To"]      = to
    msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP(host, port) as server:
        server.ehlo()
        server.starttls()
        server.login(user, password)
        server.sendmail(from_, to.split(","), msg.as_string())

    print(f"Report enviado para {to}")


# ── Campaign-level alerts ─────────────────────────────────────────────────────

def _get_alert_configs() -> list[dict]:
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT ac.id, ac.campaign_id, c.name, ac.alert_type, ac.threshold, ac.email_to
                FROM alert_configs ac
                JOIN campaigns c ON c.id = ac.campaign_id
                WHERE ac.enabled = true AND ac.email_to <> ''
            """)
            rows = cur.fetchall()
    return [{"id": r[0], "campaign_id": r[1], "campaign_name": r[2],
             "alert_type": r[3], "threshold": r[4], "email_to": r[5]}
            for r in rows]


def _has_ingestion(campaign_id: int, data_type: str) -> bool:
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM ingestion_cache WHERE campaign_id=%s AND data_type=%s LIMIT 1",
                (campaign_id, data_type),
            )
            return cur.fetchone() is not None


def _send_alert_email(to: str, subject: str, body_html: str) -> None:
    host     = os.environ["SMTP_HOST"]
    port     = int(os.environ.get("SMTP_PORT", "587"))
    user     = os.environ["SMTP_USER"]
    password = os.environ["SMTP_PASS"]
    from_    = os.environ.get("REPORT_FROM", user)
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = from_
    msg["To"]      = to
    msg.attach(MIMEText(body_html, "html", "utf-8"))
    with smtplib.SMTP(host, port) as srv:
        srv.ehlo(); srv.starttls(); srv.login(user, password)
        srv.sendmail(from_, to.split(","), msg.as_string())


def send_campaign_alerts(df: pd.DataFrame) -> None:
    """Check alert_configs and dispatch per-campaign emails if conditions are met."""
    configs = _get_alert_configs()
    if not configs:
        return

    today = pd.Timestamp.now().normalize()
    today_str = datetime.now().strftime("%d/%m/%Y")

    for cfg in configs:
        cid    = cfg["campaign_id"]
        cname  = cfg["campaign_name"]
        atype  = cfg["alert_type"]
        thr    = cfg["threshold"]
        to     = cfg["email_to"]

        triggered = False
        detail    = ""

        if atype == "ending_soon":
            if not df.empty and "sys_campaign" in df.columns:
                camp_df = df[df["sys_campaign"] == cname]
                if not camp_df.empty and "end_date" in camp_df.columns:
                    deadline = today + pd.Timedelta(days=thr)
                    soon = camp_df[
                        camp_df["end_date"].notna() &
                        (camp_df["end_date"] >= today) &
                        (camp_df["end_date"] <= deadline)
                    ]
                    if not soon.empty:
                        triggered = True
                        detail = f"{len(soon)} peça(s) encerram em ≤{thr} dias."

        elif atype == "no_plan":
            if not _has_ingestion(cid, "plan"):
                triggered = True
                detail = "Nenhum plano cadastrado para esta campanha."

        elif atype == "no_assets":
            if not _has_ingestion(cid, "assets"):
                triggered = True
                detail = "Nenhum asset cadastrado para esta campanha."

        elif atype == "over_budget":
            if not df.empty and "sys_campaign" in df.columns:
                camp_df = df[df["sys_campaign"] == cname]
                if not camp_df.empty and "budget" in camp_df.columns and "spend" in camp_df.columns:
                    def _n(s):
                        try:
                            return float(str(s).replace("R$","").replace(".","").replace(",",".").strip())
                        except Exception:
                            return 0.0
                    tot_bud = camp_df["budget"].apply(_n).sum()
                    tot_spd = camp_df["spend"].apply(_n).sum()
                    if tot_bud > 0 and (tot_spd / tot_bud * 100) >= thr:
                        triggered = True
                        detail = f"Gasto ({tot_spd:,.0f}) atingiu {thr}% do orçamento ({tot_bud:,.0f})."

        if triggered:
            alert_labels = {
                "ending_soon": "⏰ Campanha encerrando em breve",
                "no_plan":     "⚠️ Sem plano cadastrado",
                "no_assets":   "⚠️ Sem assets cadastrados",
                "over_budget": "💸 Orçamento atingido",
            }
            subject = f"[Campanha PPG] {alert_labels.get(atype, atype)} — {cname}"
            html = f"""<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;padding:24px;background:#f0f4f8">
<div style="max-width:560px;margin:0 auto;background:#fff;border-radius:8px;padding:24px;box-shadow:0 2px 8px rgba(0,0,0,.08)">
  <h2 style="color:#1e293b">{alert_labels.get(atype, atype)}</h2>
  <p style="color:#475569"><b>Campanha:</b> {cname}</p>
  <p style="color:#475569">{detail}</p>
  <hr style="border:none;border-top:1px solid #e2e8f0">
  <p style="color:#94a3b8;font-size:11px">Controle de Campanhas PPG · {today_str}</p>
</div></body></html>"""
            try:
                _send_alert_email(to, subject, html)
                print(f"[alerta] {atype} enviado para {to} — campanha: {cname}")
            except Exception as exc:
                print(f"[alerta] erro ao enviar {atype} para {to}: {exc}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    print("Coletando dados do banco...")
    raw, no_data = gather_plan_data()

    if raw.empty:
        print("Nenhum plano encontrado — apenas a seção 'Sem dados' será enviada.")
        html = build_html(pd.DataFrame(), no_data)
        send_email(html)
        return

    raw = deduplicate(raw)
    df  = compute_status(raw)

    status_counts = df["_status"].value_counts().to_dict()
    print(f"[diagnóstico] status após compute_status: {status_counts}")
    print(f"{len(df)} criativos processados.")

    html = build_html(df, no_data)
    send_email(html)
    send_campaign_alerts(df)


if __name__ == "__main__":
    main()
