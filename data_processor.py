import io
import unicodedata

import pandas as pd
import requests
from rapidfuzz import fuzz, process

FIELD_LABELS: dict[str, str] = {
    "campaign_name": "Nome da Campanha",
    "ad_group":      "Grupo de Anúncio",
    "ad_name":       "Anúncio",
    "start_date":    "Data de Início",
    "end_date":      "Data de Fim",
    "budget":        "Orçamento (R$)",
    "vehicle":       "Veículo / Canal",
    "date":          "Data",
    "spend":         "Valor Gasto",
    "impressions":   "Impressões",
    "clicks":        "Cliques",
    "views":         "Views",
    "asset_id":      "ID da Peça",
    "format":        "Formato",
    "status":        "Status",
    "asset_link":    "Link do Asset",
}

PLAN_FIELDS  = ["campaign_name", "ad_group", "ad_name", "start_date", "end_date", "budget"]
ASSET_FIELDS = ["campaign_name", "ad_group", "ad_name", "vehicle", "date", "spend", "impressions", "clicks", "views"]


def get_sheets(file_obj) -> list[str]:
    try:
        return pd.ExcelFile(file_obj).sheet_names
    except Exception:
        return []


def _xlsx_url(url: str) -> str:
    """Normalize any Google Sheets URL to an XLSX export URL."""
    if "docs.google.com/spreadsheets" in url:
        base = url.split("/edit")[0].split("/pub")[0]
        return f"{base}/export?format=xlsx"
    return url


def get_sheets_from_url(url: str) -> list[str]:
    """Download file from URL and return sheet names. Returns [] for plain CSV."""
    try:
        resp = requests.get(_xlsx_url(url), timeout=30)
        resp.raise_for_status()
        return pd.ExcelFile(io.BytesIO(resp.content)).sheet_names
    except Exception:
        return []


def _flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Collapse MultiIndex or tuple-valued columns into plain strings."""
    def _join(col) -> str:
        parts = col if isinstance(col, tuple) else (col,)
        return " ".join(
            str(s) for s in parts
            if str(s).strip() and not str(s).startswith("Unnamed")
        ).strip() or str(col)

    if isinstance(df.columns, pd.MultiIndex) or any(
        isinstance(c, tuple) for c in df.columns
    ):
        df.columns = [_join(c) for c in df.columns]
    else:
        df.columns = [str(c) for c in df.columns]
    return df


def read_file(
    source_type: str,
    file_obj=None,
    url: str | None = None,
    sheet_name: int | str = 0,
    header_row: int | list[int] = 0,
) -> pd.DataFrame | None:
    if source_type == "upload" and file_obj is not None:
        if file_obj.name.lower().endswith(".csv"):
            file_obj.seek(0)
            return _flatten_columns(pd.read_csv(file_obj, header=header_row))
        xl = pd.ExcelFile(file_obj)
        return _flatten_columns(xl.parse(sheet_name=sheet_name, header=header_row))

    if source_type == "url" and url:
        resp = requests.get(_xlsx_url(url), timeout=30)
        resp.raise_for_status()
        ct = resp.headers.get("content-type", "")
        if "text/plain" in ct or "text/csv" in ct:
            return _flatten_columns(pd.read_csv(io.StringIO(resp.text), header=header_row))
        return _flatten_columns(
            pd.read_excel(io.BytesIO(resp.content), sheet_name=sheet_name, header=header_row)
        )
    return None


def apply_mapping(df: pd.DataFrame, mapping: dict[str, str]) -> pd.DataFrame:
    """mapping = {standard_field: original_column_name}"""
    rename = {
        orig: std
        for std, orig in mapping.items()
        if orig and orig != "(não mapear)" and orig in df.columns
    }
    return df.rename(columns=rename)


def normalize_dates(df: pd.DataFrame, fields: list[str]) -> pd.DataFrame:
    import datetime
    current_year = str(datetime.datetime.now().year)

    def _fix_year(val):
        if pd.isna(val): return val
        v_str = str(val).strip()
        if v_str.count('/') == 1 and v_str.count('-') == 0:
            return v_str + '/' + current_year
        if v_str.count('-') == 1 and v_str.count('/') == 0:
            return v_str + '-' + current_year
        return val

    for f in fields:
        if f in df.columns:
            # Extrair a data (permite dia/mês com ou sem ano, ignora o resto)
            extracted = df[f].astype(str).str.extract(r"(\d{1,4}[/-]\d{1,2}(?:[/-]\d{1,4})?)", expand=False)
            extracted = extracted.apply(_fix_year)
            df[f] = pd.to_datetime(extracted.fillna(df[f]), errors="coerce", dayfirst=True, format="mixed")
    return df


TAXONOMY_JOIN_FIELDS = ["campaign_name", "ad_group", "ad_name"]


def _remove_accents(s: pd.Series) -> pd.Series:
    return s.apply(
        lambda x: unicodedata.normalize("NFKD", str(x)).encode("ascii", "ignore").decode("ascii")
    )


def _composite_key(df: pd.DataFrame, fields: list[str]) -> pd.Series:
    """Normalized composite key from multiple columns joined with '||'."""
    parts = [
        _remove_accents(df[f].fillna("").astype(str))
        .str.strip().str.lower().str.replace(r"\s+", " ", regex=True)
        for f in fields if f in df.columns
    ]
    if not parts:
        return pd.Series("", index=df.index)
    key = parts[0]
    for p in parts[1:]:
        key = key + "||" + p
    return key


METRIC_SUM_COLS = ["spend", "impressions", "clicks", "views"]


def aggregate_assets(
    assets_df: pd.DataFrame,
    group_fields: list[str],
) -> pd.DataFrame:
    """Collapse daily rows into one row per creative.

    - Metric columns (spend, impressions, clicks, views) → sum
    - date → max (last serving date)
    - Other columns → first value
    """
    available_group = [f for f in group_fields if f in assets_df.columns]
    if "vehicle" in assets_df.columns and "vehicle" not in available_group:
        available_group = available_group + ["vehicle"]
    if not available_group:
        return assets_df

    agg: dict[str, str] = {}
    for col in assets_df.columns:
        if col in available_group:
            continue
        if col == "date":
            agg[col] = "max"
        elif col in METRIC_SUM_COLS:
            agg[col] = "sum"
        else:
            agg[col] = "first"

    if not agg:
        return assets_df

    result = assets_df.groupby(available_group, as_index=False, dropna=False).agg(agg)
    return result.reset_index(drop=True)


def merge_taxonomy(
    plan_df: pd.DataFrame,
    assets_df: pd.DataFrame,
    join_fields: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Left join on a compound taxonomy key (campaign / ad_group / ad_name)."""
    p = plan_df.copy()
    a = assets_df.copy()
    p["__jk"] = _composite_key(p, join_fields)
    a["__jk"] = _composite_key(a, join_fields)

    merged = p.merge(
        a, on="__jk", how="left", suffixes=("", "_asset"), indicator=True,
    )
    drop_cols = ["__jk", "_merge"]
    matched   = merged[merged["_merge"] == "both"].drop(columns=drop_cols, errors="ignore")
    unmatched = merged[merged["_merge"] == "left_only"].drop(columns=drop_cols, errors="ignore")
    unmatched = unmatched[list(plan_df.columns)]
    return matched.reset_index(drop=True), unmatched.reset_index(drop=True)


def _per_field_score(
    plan_row: pd.Series,
    asset_row: pd.Series,
    fields: list[str],
) -> float:
    """Average token_sort_ratio across individual fields (preserves field boundaries)."""
    scores = []
    for f in fields:
        pv = _remove_accents(pd.Series([str(plan_row.get(f, ""))])).str.strip().str.lower().str.replace(r"\s+", " ", regex=True).iloc[0]
        av = _remove_accents(pd.Series([str(asset_row.get(f, ""))])).str.strip().str.lower().str.replace(r"\s+", " ", regex=True).iloc[0]
        scores.append(fuzz.token_sort_ratio(pv, av))
    return sum(scores) / len(scores) if scores else 0.0


def fuzzy_merge_taxonomy(
    plan_df: pd.DataFrame,
    assets_df: pd.DataFrame,
    join_fields: list[str],
    threshold: int = 80,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Exact merge first; for unmatched plan rows tries per-field fuzzy match >= threshold."""
    exact_matched, unmatched = merge_taxonomy(plan_df, assets_df, join_fields)

    if unmatched.empty:
        return exact_matched, unmatched

    a = assets_df.copy()
    a["__jk"] = _composite_key(a, join_fields)
    asset_unique = a.drop_duplicates(subset=["__jk"])

    fuzzy_rows = []
    still_unmatched = []

    for _, prow in unmatched.iterrows():
        best_score = -1.0
        best_jk    = None
        for _, arow in asset_unique.iterrows():
            score = _per_field_score(prow, arow, join_fields)
            if score > best_score:
                best_score = score
                best_jk    = arow["__jk"]

        if best_score >= threshold and best_jk is not None:
            for _, arow in a[a["__jk"] == best_jk].iterrows():
                row = prow.to_dict()
                for col, val in arow.items():
                    if col == "__jk":
                        continue
                    if col in row:
                        row[f"{col}_asset"] = val
                    else:
                        row[col] = val
                row["_match_type"] = f"fuzzy ({int(best_score)}%)"
                fuzzy_rows.append(row)
        else:
            still_unmatched.append(prow.to_dict())

    exact_matched = exact_matched.copy()
    exact_matched["_match_type"] = "exato"
    if fuzzy_rows:
        fuzzy_df = pd.DataFrame(fuzzy_rows)
        all_matched = pd.concat([exact_matched, fuzzy_df], ignore_index=True)
    else:
        all_matched = exact_matched

    remaining = (
        pd.DataFrame(still_unmatched).reset_index(drop=True)
        if still_unmatched else unmatched.iloc[0:0]
    )
    return all_matched, remaining


def fuzzy_taxonomy_report(
    plan_df: pd.DataFrame,
    assets_df: pd.DataFrame,
    join_fields: list[str],
    threshold: int = 80,
) -> pd.DataFrame:
    """Fuzzy report on compound taxonomy key."""
    sep = " | "

    def _display_key(df, fields):
        parts = [
            df[f].astype(str).str.strip().fillna("")
            for f in fields if f in df.columns
        ]
        if not parts:
            return pd.Series("", index=df.index)
        key = parts[0]
        for p in parts[1:]:
            key = key + sep + p
        return key

    plan_keys  = _display_key(plan_df,  join_fields).unique().tolist()
    asset_keys = _display_key(assets_df, join_fields).unique().tolist()

    def _norm(s: str) -> str:
        return unicodedata.normalize("NFKD", s.lower()).encode("ascii", "ignore").decode("ascii").strip()

    exact = {_norm(k) for k in asset_keys}

    # Build per-field normalized lookup for asset rows
    asset_rows_norm = []
    for k in asset_keys:
        parts = k.split(sep)
        asset_rows_norm.append({f: parts[i] if i < len(parts) else "" for i, f in enumerate(join_fields)})

    rows = []
    for val in plan_keys:
        if _norm(val) in exact:
            continue
        plan_parts = val.split(sep)
        plan_row = {f: plan_parts[i] if i < len(plan_parts) else "" for i, f in enumerate(join_fields)}
        best_score = -1.0
        best_key   = None
        for ak, ar in zip(asset_keys, asset_rows_norm):
            score = _per_field_score(plan_row, ar, join_fields)
            if score > best_score:
                best_score = score
                best_key   = ak
        if best_key is not None:
            rows.append({
                "Chave no Plano": val,
                "Melhor Match":   best_key,
                "Score (%)":      int(best_score),
                "Sugestão":       "✅ Corrigir" if best_score >= threshold else "⚠️ Revisar",
            })

    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["Chave no Plano", "Melhor Match", "Score (%)", "Sugestão"]
    )


def merge_data(
    plan_df: pd.DataFrame,
    assets_df: pd.DataFrame,
    plan_key: str,
    asset_key: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    p = plan_df.copy()
    a = assets_df.copy()
    p["__jk"]  = p[plan_key].astype(str).str.strip().str.lower()
    a["__jka"] = a[asset_key].astype(str).str.strip().str.lower()

    merged = p.merge(
        a, left_on="__jk", right_on="__jka",
        how="left", suffixes=("", "_asset"), indicator=True,
    )
    drop_cols = ["__jk", "__jka", "_merge"]
    matched   = merged[merged["_merge"] == "both"].drop(columns=drop_cols, errors="ignore")
    unmatched = merged[merged["_merge"] == "left_only"].drop(columns=drop_cols, errors="ignore")
    unmatched = unmatched[list(plan_df.columns)]
    return matched.reset_index(drop=True), unmatched.reset_index(drop=True)


def fuzzy_match_report(
    plan_df: pd.DataFrame,
    assets_df: pd.DataFrame,
    plan_key: str,
    asset_key: str,
    threshold: int = 80,
) -> pd.DataFrame:
    plan_vals  = plan_df[plan_key].dropna().astype(str).str.strip().unique().tolist()
    asset_vals = assets_df[asset_key].dropna().astype(str).str.strip().unique().tolist()
    exact = set(asset_vals)

    rows = []
    for val in plan_vals:
        if val in exact:
            continue
        m = process.extractOne(val, asset_vals, scorer=fuzz.token_sort_ratio)
        if m:
            rows.append({
                "Valor no Plano": val,
                "Melhor Match":   m[0],
                "Score (%)":      int(m[1]),
                "Sugestão":       "✅ Corrigir" if m[1] >= threshold else "⚠️ Revisar",
            })

    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["Valor no Plano", "Melhor Match", "Score (%)", "Sugestão"]
    )


def read_campaign_sheet(
    sheet_url: str,
    sheet_name: str | int = 0,
    header_row: int = 0,
    col_cliente: str = "",
    col_campanha: str = "",
    col_inicio: str = "",
    col_fim: str = "",
    col_veiculos: str = "",
    col_link_plano: str = "",
    col_link_dash: str = "",
) -> pd.DataFrame:
    """Read campaign data from a Google Sheets URL and return a normalized DataFrame.

    Returned columns:
        cliente, campanha, data_inicio, data_fim, veiculos, link_plano, link_dash, status_campanha, dias_restantes
    """
    df = read_file("url", url=sheet_url, sheet_name=sheet_name, header_row=header_row)
    if df is None or df.empty:
        return pd.DataFrame(columns=[
            "cliente", "campanha", "data_inicio", "data_fim", "veiculos", "link_plano", "link_dash", "status_campanha", "dias_restantes",
        ])

    # Rename mapped columns to canonical names
    rename_map = {}
    if col_cliente and col_cliente in df.columns:
        rename_map[col_cliente] = "cliente"
    if col_campanha and col_campanha in df.columns:
        rename_map[col_campanha] = "campanha"
    if col_inicio and col_inicio in df.columns:
        rename_map[col_inicio] = "data_inicio"
    if col_fim and col_fim in df.columns:
        rename_map[col_fim] = "data_fim"
    if col_veiculos and col_veiculos in df.columns:
        rename_map[col_veiculos] = "veiculos"
    if col_link_plano and col_link_plano in df.columns:
        rename_map[col_link_plano] = "link_plano"
    if col_link_dash and col_link_dash in df.columns:
        rename_map[col_link_dash] = "link_dash"
    df = df.rename(columns=rename_map)

    # Ensure canonical columns exist
    for col in ["cliente", "campanha", "data_inicio", "data_fim", "veiculos", "link_plano", "link_dash"]:
        if col not in df.columns:
            df[col] = ""

    # Drop rows where campanha is empty
    df = df[df["campanha"].astype(str).str.strip() != ""].copy()

    # Parse dates
    today = pd.Timestamp.now().normalize()
    df["data_inicio"] = pd.to_datetime(df["data_inicio"], errors="coerce", dayfirst=True, format="mixed")
    df["data_fim"] = pd.to_datetime(df["data_fim"], errors="coerce", dayfirst=True, format="mixed")

    # Compute campaign status
    def _status(row):
        ini = row["data_inicio"]
        fim = row["data_fim"]

        if pd.isna(ini) and pd.isna(fim):
            return "⏳ Sem datas", None

        if pd.notna(fim) and fim < today:
            elapsed = (today - fim).days
            return "🏁 Finalizada", -elapsed

        if pd.notna(ini) and ini > today:
            until = (ini - today).days
            return "📅 Aguardando início", until

        if pd.notna(fim):
            remaining = (fim - today).days
            return "🟢 Em veiculação", remaining

        return "🟢 Em veiculação", None

    status_info = df.apply(_status, axis=1, result_type="expand")
    df["status_campanha"] = status_info[0]
    df["dias_restantes"] = status_info[1]

    # Clean up veiculos column
    df["veiculos"] = df["veiculos"].fillna("").astype(str).str.strip()
    df["cliente"] = df["cliente"].fillna("").astype(str).str.strip()
    df["campanha"] = df["campanha"].fillna("").astype(str).str.strip()

    return df.reset_index(drop=True)


def compute_veiculacao_status(df: pd.DataFrame) -> pd.DataFrame:
    """
    Rules (based on max(date) from assets and end_date from plan):

    With end_date:
      max(date) > end_date                    → ⚠️ Ativo após data de fim
      max(date) <= end_date, end_date >= today → ▶️ Em veiculação
      max(date) <= end_date, end_date < today  → ✅ Veiculado

    Without end_date, with asset date:
      has date  → ▶️ Em veiculação
      no date   → ❌ Sem dados de veiculação

    Without asset date:
      active metrics → ▶️ Em veiculação
      no metrics     → ❌ Sem dados de veiculação
    """
    df = df.copy()
    today = pd.Timestamp.now().normalize()

    def _metric(col: str) -> pd.Series:
        # Prefer col_asset when the non-suffixed column exists in plan but is empty
        for name in (f"{col}_asset", col):
            if name in df.columns:
                s = pd.to_numeric(df[name], errors="coerce").fillna(0)
                if (s != 0).any():
                    return s
        return pd.Series(0, index=df.index, dtype=float)

    def _date_col() -> tuple[pd.Series, pd.Series]:
        for name in ("date_asset", "date"):
            if name in df.columns:
                s = pd.to_datetime(df[name], errors="coerce")
                if s.notna().any():
                    return s, s.notna()
        return (pd.Series(pd.NaT, index=df.index, dtype="datetime64[ns]"),
                pd.Series(False, index=df.index))

    impressions = _metric("impressions")
    spend       = _metric("spend")
    clicks      = _metric("clicks")
    views       = _metric("views")
    active      = (impressions > 0) | (spend > 0) | (clicks > 0) | (views > 0)

    status = pd.Series("❌ Sem dados de veiculação", index=df.index)

    asset_date, has_asset_date = _date_col()

    if "end_date" in df.columns:
        end_date = pd.to_datetime(df["end_date"], errors="coerce")
        has_end  = end_date.notna()

        after_end   = has_asset_date & has_end & (asset_date > end_date)
        within_plan = has_asset_date & has_end & (asset_date <= end_date)
        no_end      = has_asset_date & ~has_end
        
        # Se a última veiculação foi há mais de 2 dias de hoje, assumimos que já parou de veicular
        is_finished = (today - asset_date).dt.days > 2

        status[after_end & ~is_finished]               = "⚠️ Ativo após data de fim"
        status[after_end & is_finished]                = "🏁 Veiculado"
        status[within_plan & (end_date >= today)]      = "▶️ Em veiculação"
        status[within_plan & (end_date < today)]       = "🏁 Veiculado"
        status[no_end & has_asset_date]                = "▶️ Em veiculação"
        status[~has_asset_date & has_end &  active]    = "▶️ Em veiculação"
        status[~has_asset_date & has_end & ~active]    = "❌ Sem dados de veiculação"
        status[~has_asset_date & ~has_end &  active]   = "▶️ Em veiculação"
        status[~has_asset_date & ~has_end & ~active]   = "❌ Sem dados de veiculação"
    else:
        status[has_asset_date]                = "▶️ Em veiculação"
        status[~has_asset_date &  active]     = "▶️ Em veiculação"
        status[~has_asset_date & ~active]     = "❌ Sem dados de veiculação"

    df["veiculacao_status"] = status
    return df
