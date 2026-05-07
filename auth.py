import hashlib
import io
import json
import os
import pickle
import secrets
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st
import psycopg2
from dotenv import load_dotenv
from contextlib import contextmanager

load_dotenv()
DB_URL = os.getenv("DATABASE_URL") or st.secrets.get("DATABASE_URL", "")

@contextmanager
def get_db():
    conn = psycopg2.connect(DB_URL)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def _hash(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()

def init_db() -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id            SERIAL PRIMARY KEY,
                    username      TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role          TEXT NOT NULL CHECK(role IN ('admin','viewer'))
                );
                CREATE TABLE IF NOT EXISTS clients (
                    name       TEXT PRIMARY KEY,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS campaigns (
                    id         SERIAL PRIMARY KEY,
                    name       TEXT UNIQUE NOT NULL,
                    client_name TEXT NOT NULL DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS vehicles (
                    id          SERIAL PRIMARY KEY,
                    campaign_id INTEGER NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
                    name        TEXT NOT NULL,
                    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(campaign_id, name)
                );
                CREATE TABLE IF NOT EXISTS mapping_templates (
                    id            SERIAL PRIMARY KEY,
                    client_name   TEXT NOT NULL,
                    template_name TEXT NOT NULL,
                    source_type   TEXT NOT NULL,
                    mapping_json  TEXT NOT NULL,
                    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(client_name, template_name)
                );
                CREATE TABLE IF NOT EXISTS ingestion_cache (
                    id           SERIAL PRIMARY KEY,
                    campaign_id  INTEGER NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
                    vehicle_id   INTEGER NOT NULL REFERENCES vehicles(id)  ON DELETE CASCADE,
                    data_type    TEXT NOT NULL CHECK(data_type IN ('plan','assets')),
                    data_blob    BYTEA NOT NULL,
                    mapping_json TEXT NOT NULL DEFAULT '{}',
                    source_info  TEXT NOT NULL DEFAULT '',
                    config_json  TEXT NOT NULL DEFAULT '{}',
                    updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(campaign_id, vehicle_id, data_type)
                );
                CREATE TABLE IF NOT EXISTS user_state (
                    username    TEXT PRIMARY KEY,
                    campaign_id INTEGER REFERENCES campaigns(id) ON DELETE SET NULL,
                    vehicle_id  INTEGER REFERENCES vehicles(id)  ON DELETE SET NULL,
                    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS user_client_access (
                    username    TEXT NOT NULL REFERENCES users(username) ON DELETE CASCADE,
                    client_name TEXT NOT NULL,
                    PRIMARY KEY (username, client_name)
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token      TEXT PRIMARY KEY,
                    username   TEXT NOT NULL REFERENCES users(username) ON DELETE CASCADE,
                    role       TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS campaign_sheets_config (
                    id              SERIAL PRIMARY KEY,
                    sheet_url       TEXT NOT NULL,
                    sheet_name      TEXT NOT NULL DEFAULT '',
                    col_cliente     TEXT NOT NULL DEFAULT '',
                    col_campanha    TEXT NOT NULL DEFAULT '',
                    col_inicio      TEXT NOT NULL DEFAULT '',
                    col_fim         TEXT NOT NULL DEFAULT '',
                    col_veiculos    TEXT NOT NULL DEFAULT '',
                    col_link_plano  TEXT NOT NULL DEFAULT '',
                    col_link_dash   TEXT NOT NULL DEFAULT '',
                    header_row      INTEGER NOT NULL DEFAULT 1,
                    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS ingestion_log (
                    id           SERIAL PRIMARY KEY,
                    campaign_id  INTEGER NOT NULL,
                    vehicle_id   INTEGER NOT NULL,
                    data_type    TEXT NOT NULL,
                    username     TEXT NOT NULL DEFAULT '',
                    row_count    INTEGER NOT NULL DEFAULT 0,
                    source_info  TEXT NOT NULL DEFAULT '',
                    ts           TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS alert_configs (
                    id           SERIAL PRIMARY KEY,
                    campaign_id  INTEGER REFERENCES campaigns(id) ON DELETE CASCADE,
                    alert_type   TEXT NOT NULL,
                    threshold    INTEGER NOT NULL DEFAULT 7,
                    email_to     TEXT NOT NULL DEFAULT '',
                    enabled      BOOLEAN NOT NULL DEFAULT true,
                    created_by   TEXT NOT NULL DEFAULT '',
                    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS report_recipients (
                    id          SERIAL PRIMARY KEY,
                    client_name TEXT NOT NULL,
                    email       TEXT NOT NULL,
                    active      BOOLEAN NOT NULL DEFAULT true,
                    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(client_name, email)
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id          SERIAL PRIMARY KEY,
                    username    TEXT NOT NULL DEFAULT '',
                    action      TEXT NOT NULL,
                    entity_type TEXT NOT NULL DEFAULT '',
                    entity_name TEXT NOT NULL DEFAULT '',
                    details     TEXT NOT NULL DEFAULT '',
                    ts          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS vehicle_notes (
                    id          SERIAL PRIMARY KEY,
                    vehicle_id  INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
                    campaign_id INTEGER NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
                    username    TEXT NOT NULL DEFAULT '',
                    note        TEXT NOT NULL,
                    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS login_log (
                    id       SERIAL PRIMARY KEY,
                    username TEXT NOT NULL,
                    success  BOOLEAN NOT NULL,
                    ts       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS system_config (
                    key   TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS alias_mapping (
                    id         SERIAL PRIMARY KEY,
                    field      TEXT NOT NULL,
                    source_term TEXT NOT NULL,
                    target_term TEXT NOT NULL,
                    created_by  TEXT,
                    created_at  TIMESTAMP DEFAULT NOW(),
                    UNIQUE(field, source_term)
                )
            """)
            cur.execute("""
                ALTER TABLE ingestion_cache
                ADD COLUMN IF NOT EXISTS updated_by TEXT NOT NULL DEFAULT ''
            """)
            cur.execute("""
                ALTER TABLE campaigns
                ADD COLUMN IF NOT EXISTS archived BOOLEAN NOT NULL DEFAULT false
            """)
            cur.execute("""
                ALTER TABLE ingestion_log
                ADD COLUMN IF NOT EXISTS data_blob BYTEA
            """)
            cur.execute("""
                ALTER TABLE ingestion_log
                ADD COLUMN IF NOT EXISTS mapping_json TEXT NOT NULL DEFAULT '{}'
            """)
            cur.execute("""
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS email TEXT NOT NULL DEFAULT ''
            """)
            cur.execute("""
                ALTER TABLE sessions
                ADD COLUMN IF NOT EXISTS last_activity TEXT NOT NULL DEFAULT ''
            """)
            
            cur.execute("""
                INSERT INTO users (username, password_hash, role) 
                VALUES (%s, %s, %s)
                ON CONFLICT (username) DO NOTHING
            """, ("admin", _hash("admin123"), "admin"))
            
            cur.execute("""
                INSERT INTO users (username, password_hash, role) 
                VALUES (%s, %s, %s)
                ON CONFLICT (username) DO NOTHING
            """, ("viewer", _hash("viewer123"), "viewer"))


def verify_login(username: str, password: str) -> str | None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT role FROM users WHERE username=%s AND password_hash=%s",
                (username, _hash(password)),
            )
            row = cur.fetchone()
    return row[0] if row else None


def create_session(username: str, role: str, days: int = 7) -> str:
    token = secrets.token_hex(32)
    expires = (datetime.utcnow() + timedelta(days=days)).isoformat()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO sessions (token, username, role, expires_at) VALUES (%s,%s,%s,%s)",
                (token, username, role, expires),
            )
    return token


@st.cache_data(ttl=120, show_spinner=False)
def validate_session(token: str) -> tuple[str, str] | None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT username, role, expires_at, last_activity FROM sessions WHERE token=%s",
                (token,),
            )
            row = cur.fetchone()
    if not row:
        return None
    username, role, expires_at, last_activity = row
    now = datetime.utcnow()
    if now > datetime.fromisoformat(expires_at):
        delete_session(token)
        return None
    # Inactivity timeout check
    timeout_hours = int(get_system_config("session_timeout_hours", "8"))
    if last_activity:
        try:
            idle = (now - datetime.fromisoformat(last_activity)).total_seconds() / 3600
            if idle > timeout_hours:
                delete_session(token)
                return None
        except ValueError:
            pass
    # Update last_activity (bypass cache — direct write)
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE sessions SET last_activity=%s WHERE token=%s",
                    (now.isoformat(), token),
                )
    except Exception:
        pass
    return username, role


def delete_session(token: str) -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM sessions WHERE token=%s", (token,))


def login_ui() -> None:
    st.markdown(
        "<h2 style='text-align:center;padding-top:3rem'>📊 Controle de Campanhas PPG</h2>"
        "<p style='text-align:center;color:#8b949e'>Campaign Management Platform</p>",
        unsafe_allow_html=True,
    )
    _, mid, _ = st.columns([1, 1.4, 1])
    with mid:
        st.divider()
        user = st.text_input("Usuário", placeholder="admin ou viewer")
        pw = st.text_input("Senha", type="password")
        if st.button("Entrar →", type="primary", use_container_width=True):
            role = verify_login(user, pw)
            if role:
                log_login(user, success=True)
                log_audit(user, "login", details="Login realizado com sucesso")
                st.session_state.update(
                    logged_in=True, username=user, role=role, _just_logged_in=True
                )
                st.rerun()
            else:
                log_login(user.strip() or "?", success=False)
                st.error("Usuário ou senha inválidos.")


_PARQUET_MAGIC = b"\x00PQT\x00"  # prefix that identifies parquet-encoded blobs


def save_ingestion(campaign_id: int, vehicle_id: int, data_type: str,
                   df, mapping: dict, source_info: str = "", config_json: str = "{}",
                   username: str = "") -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq

    df = df.copy()

    # Constrói o schema pyarrow explicitamente para cada coluna,
    # forçando colunas object para string — evita inferência de tipo errada
    # (ex.: coluna com valores como 'R 195.598,50' sendo inferida como double).
    pa_fields = []
    for col in df.columns:
        if df[col].dtype == object:
            # Converte todos os valores para str (None para nulos)
            df[col] = df[col].apply(
                lambda x: None if (x is None or (isinstance(x, float) and x != x)) else str(x)
            )
            pa_fields.append(pa.field(str(col), pa.string()))
        elif pd.api.types.is_datetime64_any_dtype(df[col]):
            pa_fields.append(pa.field(str(col), pa.timestamp("us")))
        elif pd.api.types.is_integer_dtype(df[col]):
            pa_fields.append(pa.field(str(col), pa.int64()))
        elif pd.api.types.is_float_dtype(df[col]):
            pa_fields.append(pa.field(str(col), pa.float64()))
        elif pd.api.types.is_bool_dtype(df[col]):
            pa_fields.append(pa.field(str(col), pa.bool_()))
        else:
            # Deixa o pyarrow inferir para tipos menos comuns
            arr = pa.array(df[col].tolist(), from_pandas=True)
            pa_fields.append(pa.field(str(col), arr.type))

    schema = pa.schema(pa_fields)
    table = pa.Table.from_pandas(df, schema=schema, preserve_index=False)
    buf = io.BytesIO()
    pq.write_table(table, buf)
    blob = _PARQUET_MAGIC + buf.getvalue()

    row_count = len(df)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO ingestion_cache
                (campaign_id, vehicle_id, data_type, data_blob, mapping_json, updated_at, source_info, config_json, updated_by)
                VALUES (%s,%s,%s,%s,%s,CURRENT_TIMESTAMP,%s,%s,%s)
                ON CONFLICT (campaign_id, vehicle_id, data_type)
                DO UPDATE SET
                    data_blob    = EXCLUDED.data_blob,
                    mapping_json = EXCLUDED.mapping_json,
                    updated_at   = CURRENT_TIMESTAMP,
                    source_info  = EXCLUDED.source_info,
                    config_json  = EXCLUDED.config_json,
                    updated_by   = EXCLUDED.updated_by
            """, (campaign_id, vehicle_id, data_type,
                  psycopg2.Binary(blob), json.dumps(mapping, default=str), source_info, config_json, username))
            cur.execute("""
                INSERT INTO ingestion_log
                (campaign_id, vehicle_id, data_type, username, row_count, source_info, data_blob, mapping_json)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            """, (campaign_id, vehicle_id, data_type, username, row_count, source_info,
                  psycopg2.Binary(blob), json.dumps(mapping, default=str)))
    get_ingestion_timestamps.clear()
    get_ingestion_log.clear()
    get_mapping_coverage.clear()
    get_pending_vehicles.clear()


@st.cache_data(ttl=300, show_spinner=False)
def load_ingestion(campaign_id: int, vehicle_id: int,
                   data_type: str) -> tuple:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT data_blob, mapping_json, updated_at, source_info, config_json FROM ingestion_cache
                WHERE campaign_id=%s AND vehicle_id=%s AND data_type=%s
            """, (campaign_id, vehicle_id, data_type))
            row = cur.fetchone()
    if not row:
        return None, {}, None, None, {}
    try:
        blob_data = row[0]
        if isinstance(blob_data, memoryview):
            blob_data = blob_data.tobytes()

        if blob_data.startswith(_PARQUET_MAGIC):
            df = pd.read_parquet(io.BytesIO(blob_data[len(_PARQUET_MAGIC):]), engine="pyarrow")
        else:
            # Legacy pickle blobs — still attempt to load for backward compat
            df = pickle.loads(blob_data)

        mapping = json.loads(row[1]) if row[1] else {}
        config = json.loads(row[4]) if len(row) > 4 and row[4] else {}
        return df, mapping, row[2], row[3], config
    except Exception:
        return None, {}, None, None, {}


def save_user_state(username: str, campaign_id: int, vehicle_id: int) -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO user_state
                (username, campaign_id, vehicle_id, updated_at)
                VALUES (%s,%s,%s,CURRENT_TIMESTAMP)
                ON CONFLICT (username) DO UPDATE SET
                    campaign_id = EXCLUDED.campaign_id,
                    vehicle_id = EXCLUDED.vehicle_id,
                    updated_at = CURRENT_TIMESTAMP
            """, (username, campaign_id, vehicle_id))
    load_user_state.clear()


@st.cache_data(ttl=60, show_spinner=False)
def load_user_state(username: str) -> tuple[int | None, int | None]:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT campaign_id, vehicle_id FROM user_state WHERE username=%s",
                (username,),
            )
            row = cur.fetchone()
    return (row[0], row[1]) if row else (None, None)


@st.cache_data(ttl=60, show_spinner=False)
def get_campaigns(username: str | None = None, role: str | None = None,
                  include_archived: bool = False) -> list[dict]:
    arch_filter = "" if include_archived else " AND COALESCE(archived, false) = false"
    with get_db() as conn:
        with conn.cursor() as cur:
            if role == "admin" or username is None:
                cur.execute(
                    f"SELECT id, name, COALESCE(client_name,''), COALESCE(archived,false) "
                    f"FROM campaigns WHERE 1=1{arch_filter} ORDER BY client_name, name"
                )
            else:
                cur.execute(f"""
                    SELECT c.id, c.name, COALESCE(c.client_name,''), COALESCE(c.archived,false)
                    FROM campaigns c
                    WHERE (c.client_name = ''
                       OR c.client_name IN (
                           SELECT client_name FROM user_client_access WHERE username = %s
                       )){arch_filter}
                    ORDER BY c.client_name, c.name
                """, (username,))
            rows = cur.fetchall()
    return [{"id": r[0], "name": r[1], "client_name": r[2], "archived": r[3]} for r in rows]


def create_campaign(name: str, client_name: str = "") -> int:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO campaigns (name, client_name) VALUES (%s,%s) RETURNING id",
                (name.strip(), client_name.strip()),
            )
            cid = cur.fetchone()[0]
    get_campaigns.clear()
    get_alert_counts.clear()
    return cid


def update_campaign_client(campaign_id: int, client_name: str) -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE campaigns SET client_name=%s WHERE id=%s",
                (client_name.strip(), campaign_id),
            )
    get_campaigns.clear()


@st.cache_data(ttl=60, show_spinner=False)
def get_users() -> list[dict]:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT username, role, COALESCE(email,'') FROM users ORDER BY username"
            )
            rows = cur.fetchall()
    return [{"username": r[0], "role": r[1], "email": r[2]} for r in rows]


def add_user(username: str, password: str, role: str, email: str = "") -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (username, password_hash, role, email) VALUES (%s,%s,%s,%s)",
                (username.strip(), _hash(password), role, email.strip()),
            )
    get_users.clear()


def update_user(username: str, new_password: str | None = None,
                new_role: str | None = None, new_email: str | None = None) -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            if new_password:
                cur.execute(
                    "UPDATE users SET password_hash=%s WHERE username=%s",
                    (_hash(new_password), username),
                )
            if new_role:
                cur.execute("UPDATE users SET role=%s WHERE username=%s", (new_role, username))
            if new_email is not None:
                cur.execute("UPDATE users SET email=%s WHERE username=%s", (new_email.strip(), username))
    get_users.clear()


def delete_user(username: str) -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM users WHERE username=%s", (username,))
    get_users.clear()


# ── Report recipients ─────────────────────────────────────────────────────────

@st.cache_data(ttl=60, show_spinner=False)
def get_report_recipients(client_name: str | None = None) -> list[dict]:
    with get_db() as conn:
        with conn.cursor() as cur:
            if client_name:
                cur.execute(
                    "SELECT id, client_name, email, active FROM report_recipients "
                    "WHERE client_name=%s ORDER BY email",
                    (client_name,),
                )
            else:
                cur.execute(
                    "SELECT id, client_name, email, active FROM report_recipients ORDER BY client_name, email"
                )
            rows = cur.fetchall()
    return [{"id": r[0], "client_name": r[1], "email": r[2], "active": r[3]} for r in rows]


def add_report_recipient(client_name: str, email: str) -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO report_recipients (client_name, email) VALUES (%s,%s) "
                "ON CONFLICT (client_name, email) DO UPDATE SET active=true",
                (client_name.strip(), email.strip()),
            )
    get_report_recipients.clear()


def toggle_report_recipient(recipient_id: int, active: bool) -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE report_recipients SET active=%s WHERE id=%s", (active, recipient_id))
    get_report_recipients.clear()


def delete_report_recipient(recipient_id: int) -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM report_recipients WHERE id=%s", (recipient_id,))
    get_report_recipients.clear()


# ── System config ─────────────────────────────────────────────────────────────

def get_system_config(key: str, default: str = "") -> str:
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT value FROM system_config WHERE key=%s", (key,))
                row = cur.fetchone()
        return row[0] if row else default
    except Exception:
        return default


def set_system_config(key: str, value: str) -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO system_config (key, value) VALUES (%s,%s) "
                "ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value",
                (key, value),
            )
    # get_system_config is not cached (reads directly from DB), no cache to clear


# ── Audit log ─────────────────────────────────────────────────────────────────

def log_audit(username: str, action: str, entity_type: str = "",
              entity_name: str = "", details: str = "") -> None:
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO audit_log (username, action, entity_type, entity_name, details) "
                    "VALUES (%s,%s,%s,%s,%s)",
                    (username, action, entity_type, entity_name, details),
                )
    except Exception:
        pass


@st.cache_data(ttl=30, show_spinner=False)
def get_audit_log(limit: int = 200, entity_type: str | None = None,
                  username: str | None = None) -> list[dict]:
    with get_db() as conn:
        with conn.cursor() as cur:
            filters, params = [], []
            if entity_type:
                filters.append("entity_type=%s"); params.append(entity_type)
            if username:
                filters.append("username=%s"); params.append(username)
            where = ("WHERE " + " AND ".join(filters)) if filters else ""
            params.append(limit)
            cur.execute(
                f"SELECT id, username, action, entity_type, entity_name, details, ts "
                f"FROM audit_log {where} ORDER BY ts DESC LIMIT %s",
                params,
            )
            rows = cur.fetchall()
    return [{"id": r[0], "username": r[1], "action": r[2], "entity_type": r[3],
             "entity_name": r[4], "details": r[5], "ts": r[6]} for r in rows]


# ── Vehicle notes ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=60, show_spinner=False)
def get_vehicle_notes(vehicle_id: int) -> list[dict]:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, username, note, created_at FROM vehicle_notes "
                "WHERE vehicle_id=%s ORDER BY created_at DESC",
                (vehicle_id,),
            )
            rows = cur.fetchall()
    return [{"id": r[0], "username": r[1], "note": r[2], "created_at": r[3]} for r in rows]


def add_vehicle_note(vehicle_id: int, campaign_id: int, username: str, note: str) -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO vehicle_notes (vehicle_id, campaign_id, username, note) "
                "VALUES (%s,%s,%s,%s)",
                (vehicle_id, campaign_id, username, note.strip()),
            )
    get_vehicle_notes.clear()


def delete_vehicle_note(note_id: int) -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM vehicle_notes WHERE id=%s", (note_id,))
    get_vehicle_notes.clear()


# ── Login log ─────────────────────────────────────────────────────────────────

def log_login(username: str, success: bool) -> None:
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO login_log (username, success) VALUES (%s,%s)",
                    (username, success),
                )
    except Exception:
        pass


@st.cache_data(ttl=30, show_spinner=False)
def get_login_history(username: str | None = None, limit: int = 50) -> list[dict]:
    with get_db() as conn:
        with conn.cursor() as cur:
            if username:
                cur.execute(
                    "SELECT username, success, ts FROM login_log "
                    "WHERE username=%s ORDER BY ts DESC LIMIT %s",
                    (username, limit),
                )
            else:
                cur.execute(
                    "SELECT username, success, ts FROM login_log ORDER BY ts DESC LIMIT %s",
                    (limit,),
                )
            rows = cur.fetchall()
    return [{"username": r[0], "success": r[1], "ts": r[2]} for r in rows]


# ── Alert counts (sidebar badges) ────────────────────────────────────────────

@st.cache_data(ttl=60, show_spinner=False)
def get_alert_counts(username: str | None = None, role: str | None = None) -> dict:
    today = datetime.utcnow().date()
    soon  = today + timedelta(days=7)
    with get_db() as conn:
        with conn.cursor() as cur:
            # Campaigns ending within 7 days (from campaign_sheets_config not available here
            # so we count alert_configs with ending_soon enabled)
            cur.execute("""
                SELECT COUNT(DISTINCT campaign_id) FROM alert_configs
                WHERE alert_type='ending_soon' AND enabled=true
            """)
            ending = cur.fetchone()[0] or 0

            # Campaigns without any assets in ingestion_cache
            cur.execute("""
                SELECT COUNT(DISTINCT c.id) FROM campaigns c
                JOIN vehicles v ON v.campaign_id = c.id
                WHERE COALESCE(c.archived, false) = false
                  AND NOT EXISTS (
                    SELECT 1 FROM ingestion_cache ic
                    WHERE ic.campaign_id = c.id AND ic.data_type = 'assets'
                  )
            """)
            no_assets = cur.fetchone()[0] or 0

            # Campaigns without any plan
            cur.execute("""
                SELECT COUNT(DISTINCT c.id) FROM campaigns c
                JOIN vehicles v ON v.campaign_id = c.id
                WHERE COALESCE(c.archived, false) = false
                  AND NOT EXISTS (
                    SELECT 1 FROM ingestion_cache ic
                    WHERE ic.campaign_id = c.id AND ic.data_type = 'plan'
                  )
            """)
            no_plan = cur.fetchone()[0] or 0

    return {"ending_soon": ending, "no_assets": no_assets, "no_plan": no_plan,
            "total": ending + no_assets + no_plan}


@st.cache_data(ttl=60, show_spinner=False)
def get_clients() -> list[str]:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT name FROM clients ORDER BY name"
            )
            rows = cur.fetchall()
    return [r[0] for r in rows]


def add_client(name: str) -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO clients (name) VALUES (%s) ON CONFLICT DO NOTHING", (name.strip(),))
    get_clients.clear()


def delete_client(name: str) -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM clients WHERE name=%s", (name,))
            cur.execute("DELETE FROM user_client_access WHERE client_name=%s", (name,))
            cur.execute("UPDATE campaigns SET client_name='' WHERE client_name=%s", (name,))
            cur.execute("UPDATE mapping_templates SET client_name='' WHERE client_name=%s", (name,))
    get_clients.clear()
    get_campaigns.clear()


def rename_client(old_name: str, new_name: str) -> None:
    new_name = new_name.strip()
    if not new_name or old_name == new_name:
        return
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE clients SET name=%s WHERE name=%s", (new_name, old_name))
            cur.execute("UPDATE campaigns SET client_name=%s WHERE client_name=%s", (new_name, old_name))
            cur.execute("UPDATE mapping_templates SET client_name=%s WHERE client_name=%s", (new_name, old_name))

            # Handle user_client_access safely
            cur.execute("UPDATE user_client_access SET client_name=%s WHERE client_name=%s", (new_name, old_name))
            cur.execute("DELETE FROM user_client_access WHERE client_name=%s", (old_name,))
            # Delete old client if rename was successful
            cur.execute("DELETE FROM clients WHERE name=%s AND EXISTS (SELECT 1 FROM clients WHERE name=%s)", (old_name, new_name))
    get_clients.clear()
    get_campaigns.clear()


def get_user_clients(username: str) -> list[str]:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT client_name FROM user_client_access WHERE username=%s ORDER BY client_name",
                (username,),
            )
            rows = cur.fetchall()
    return [r[0] for r in rows]


def set_user_clients(username: str, clients: list[str]) -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM user_client_access WHERE username=%s", (username,))
            for c in clients:
                if c.strip():
                    cur.execute(
                        "INSERT INTO user_client_access (username, client_name) VALUES (%s,%s) ON CONFLICT DO NOTHING",
                        (username, c.strip()),
                    )
    get_users.clear()


@st.cache_data(ttl=60, show_spinner=False)
def get_vehicles(campaign_id: int) -> list[dict]:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, name FROM vehicles WHERE campaign_id=%s ORDER BY name",
                (campaign_id,),
            )
            rows = cur.fetchall()
    return [{"id": r[0], "name": r[1]} for r in rows]


def create_vehicle(campaign_id: int, name: str) -> int:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO vehicles (campaign_id, name) VALUES (%s,%s) RETURNING id",
                (campaign_id, name.strip()),
            )
            vid = cur.fetchone()[0]
    get_vehicles.clear()
    get_campaigns.clear()
    return vid


def archive_campaign(campaign_id: int, archived: bool = True) -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE campaigns SET archived=%s WHERE id=%s", (archived, campaign_id))
    get_campaigns.clear()
    get_alert_counts.clear()


def rename_campaign(campaign_id: int, new_name: str) -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE campaigns SET name=%s WHERE id=%s", (new_name.strip(), campaign_id))
    get_campaigns.clear()
    get_alert_counts.clear()


def delete_campaign(campaign_id: int) -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM campaigns WHERE id=%s", (campaign_id,))
    get_campaigns.clear()
    get_alert_counts.clear()


def rename_vehicle(vehicle_id: int, new_name: str) -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE vehicles SET name=%s WHERE id=%s", (new_name.strip(), vehicle_id))
    get_vehicles.clear()
    get_campaigns.clear()


def delete_vehicle(vehicle_id: int) -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM vehicles WHERE id=%s", (vehicle_id,))
    get_vehicles.clear()
    get_campaigns.clear()


def has_default_password(username: str) -> bool:
    """Retorna True se o usuário ainda usa a senha padrão original."""
    default_hashes = {
        "admin":  hashlib.sha256(b"admin123").hexdigest(),
        "viewer": hashlib.sha256(b"viewer123").hexdigest(),
    }
    default_hash = default_hashes.get(username)
    if not default_hash:
        return False
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM users WHERE username=%s AND password_hash=%s",
                (username, default_hash),
            )
            return cur.fetchone() is not None


def clear_campaign_data(campaign_id: int) -> int:
    """Apaga todos os registros de ingestion_cache de uma campanha. Retorna nº de linhas removidas."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM ingestion_cache WHERE campaign_id=%s",
                (campaign_id,),
            )
            count = cur.rowcount
    get_ingestion_timestamps.clear()
    get_ingestion_log.clear()
    get_mapping_coverage.clear()
    get_pending_vehicles.clear()
    return count


def restore_ingestion_from_log(log_id: int) -> None:
    """Restaura um blob de ingestion_log de volta ao ingestion_cache."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT campaign_id, vehicle_id, data_type, data_blob, mapping_json, source_info "
                "FROM ingestion_log WHERE id=%s",
                (log_id,),
            )
            row = cur.fetchone()
    if not row:
        raise ValueError(f"Log {log_id} não encontrado.")
    campaign_id, vehicle_id, data_type, blob, mapping_json_str, source_info = row
    if blob is None:
        raise ValueError("Esta versão não tem blob salvo (ingestões antigas não têm snapshot).")
    blob_bytes = bytes(blob) if isinstance(blob, memoryview) else blob
    mapping = json.loads(mapping_json_str) if mapping_json_str else {}

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO ingestion_cache
                (campaign_id, vehicle_id, data_type, data_blob, mapping_json,
                 updated_at, source_info, config_json, updated_by)
                VALUES (%s,%s,%s,%s,%s,CURRENT_TIMESTAMP,%s,'{}','rollback')
                ON CONFLICT (campaign_id, vehicle_id, data_type) DO UPDATE SET
                    data_blob    = EXCLUDED.data_blob,
                    mapping_json = EXCLUDED.mapping_json,
                    updated_at   = CURRENT_TIMESTAMP,
                    source_info  = EXCLUDED.source_info,
                    updated_by   = EXCLUDED.updated_by
            """, (campaign_id, vehicle_id, data_type,
                  psycopg2.Binary(blob_bytes), json.dumps(mapping, default=str),
                  f"[rollback de log_id={log_id}] {source_info}"))
    get_ingestion_timestamps.clear()
    get_ingestion_log.clear()
    get_mapping_coverage.clear()
    get_pending_vehicles.clear()


def change_own_password(username: str, current_pw: str, new_pw: str) -> bool:
    """Troca a senha do usuário se current_pw estiver correta. Retorna True se OK."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM users WHERE username=%s AND password_hash=%s",
                (username, _hash(current_pw)),
            )
            if not cur.fetchone():
                return False
            cur.execute(
                "UPDATE users SET password_hash=%s WHERE username=%s",
                (_hash(new_pw), username),
            )
    get_users.clear()
    return True


@st.cache_data(ttl=60, show_spinner=False)
def get_alert_configs(campaign_id: int | None = None) -> list[dict]:
    with get_db() as conn:
        with conn.cursor() as cur:
            if campaign_id is not None:
                cur.execute(
                    "SELECT id, campaign_id, alert_type, threshold, email_to, enabled, created_by, created_at "
                    "FROM alert_configs WHERE campaign_id=%s ORDER BY alert_type",
                    (campaign_id,),
                )
            else:
                cur.execute(
                    "SELECT id, campaign_id, alert_type, threshold, email_to, enabled, created_by, created_at "
                    "FROM alert_configs ORDER BY campaign_id, alert_type"
                )
            rows = cur.fetchall()
    return [
        {"id": r[0], "campaign_id": r[1], "alert_type": r[2], "threshold": r[3],
         "email_to": r[4], "enabled": r[5], "created_by": r[6], "created_at": r[7]}
        for r in rows
    ]


def save_alert_config(campaign_id: int, alert_type: str, threshold: int,
                      email_to: str, enabled: bool, created_by: str = "") -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO alert_configs (campaign_id, alert_type, threshold, email_to, enabled, created_by)
                VALUES (%s,%s,%s,%s,%s,%s)
                ON CONFLICT DO NOTHING
            """, (campaign_id, alert_type, threshold, email_to.strip(), enabled, created_by))
    get_alert_configs.clear()
    get_alert_counts.clear()


def update_alert_config(alert_id: int, threshold: int, email_to: str, enabled: bool) -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE alert_configs SET threshold=%s, email_to=%s, enabled=%s WHERE id=%s",
                (threshold, email_to.strip(), enabled, alert_id),
            )
    get_alert_configs.clear()
    get_alert_counts.clear()


def delete_alert_config(alert_id: int) -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM alert_configs WHERE id=%s", (alert_id,))
    get_alert_configs.clear()
    get_alert_counts.clear()


@st.cache_data(ttl=60, show_spinner=False)
def get_pending_vehicles() -> list[dict]:
    """Retorna veículos ativos sem plano e/ou sem assets no ingestion_cache."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    c.id          AS campaign_id,
                    c.name        AS campaign_name,
                    c.client_name,
                    v.id          AS vehicle_id,
                    v.name        AS vehicle_name,
                    EXISTS(SELECT 1 FROM ingestion_cache ic
                           WHERE ic.vehicle_id = v.id AND ic.data_type = 'plan')   AS has_plan,
                    EXISTS(SELECT 1 FROM ingestion_cache ic
                           WHERE ic.vehicle_id = v.id AND ic.data_type = 'assets') AS has_assets
                FROM vehicles v
                JOIN campaigns c ON c.id = v.campaign_id
                WHERE COALESCE(c.archived, false) = false
                  AND (
                    NOT EXISTS(SELECT 1 FROM ingestion_cache ic
                               WHERE ic.vehicle_id = v.id AND ic.data_type = 'plan')
                    OR
                    NOT EXISTS(SELECT 1 FROM ingestion_cache ic
                               WHERE ic.vehicle_id = v.id AND ic.data_type = 'assets')
                  )
                ORDER BY c.name, v.name
            """)
            rows = cur.fetchall()
    return [
        {
            "campaign_id":   r[0],
            "campaign_name": r[1],
            "client_name":   r[2],
            "vehicle_id":    r[3],
            "vehicle_name":  r[4],
            "has_plan":      r[5],
            "has_assets":    r[6],
        }
        for r in rows
    ]


@st.cache_data(ttl=120, show_spinner=False)
def get_mapping_coverage() -> list[dict]:
    """Para cada veículo com dados no ingestion_cache, retorna % de campos mapeados."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT ic.campaign_id, c.name, ic.vehicle_id, v.name, ic.data_type, ic.mapping_json
                FROM ingestion_cache ic
                JOIN campaigns c ON c.id = ic.campaign_id
                JOIN vehicles  v ON v.id = ic.vehicle_id
                ORDER BY c.name, v.name, ic.data_type
            """)
            rows = cur.fetchall()

    from data_processor import PLAN_FIELDS, ASSET_FIELDS
    TOTAL_PLAN   = len(PLAN_FIELDS)
    TOTAL_ASSETS = len(ASSET_FIELDS)

    # Aggregate by (campaign_id, vehicle_id)
    veh_map: dict[tuple, dict] = {}
    for r in rows:
        cid, cname, vid, vname, dtype, mapping_json = r
        key = (cid, vid)
        if key not in veh_map:
            veh_map[key] = {"campaign_id": cid, "campaign": cname, "vehicle_id": vid, "vehicle": vname,
                            "plan_mapped": 0, "plan_total": TOTAL_PLAN,
                            "assets_mapped": 0, "assets_total": TOTAL_ASSETS}
        try:
            m = json.loads(mapping_json) if mapping_json else {}
        except Exception:
            m = {}
        mapped_count = sum(1 for v in m.values() if v and v != "(não mapear)")
        if dtype == "plan":
            veh_map[key]["plan_mapped"]  = mapped_count
        else:
            veh_map[key]["assets_mapped"] = mapped_count

    result = []
    for entry in veh_map.values():
        total    = entry["plan_total"] + entry["assets_total"]
        mapped   = entry["plan_mapped"] + entry["assets_mapped"]
        entry["coverage_pct"] = round(mapped / total * 100) if total else 0
        result.append(entry)
    return result


@st.cache_data(ttl=60, show_spinner=False)
def get_ingestion_timestamps(campaign_id: int, vehicle_id: int) -> dict:
    """Retorna {plan, assets, plan_by, assets_by} com updated_at e updated_by."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT data_type, updated_at, updated_by FROM ingestion_cache "
                "WHERE campaign_id=%s AND vehicle_id=%s",
                (campaign_id, vehicle_id),
            )
            rows = cur.fetchall()
    result: dict = {"plan": None, "assets": None, "plan_by": "", "assets_by": ""}
    for r in rows:
        dtype, ts, by = r[0], r[1], (r[2] if len(r) > 2 else "")
        result[dtype] = ts
        result[f"{dtype}_by"] = by or ""
    return result


@st.cache_data(ttl=30, show_spinner=False)
def get_ingestion_log(campaign_id: int | None = None, vehicle_id: int | None = None, limit: int = 50) -> list[dict]:
    """Retorna histórico de atualizações de ingestão."""
    with get_db() as conn:
        with conn.cursor() as cur:
            if campaign_id is not None and vehicle_id is not None:
                cur.execute(
                    "SELECT campaign_id, vehicle_id, data_type, username, row_count, source_info, ts "
                    "FROM ingestion_log WHERE campaign_id=%s AND vehicle_id=%s ORDER BY ts DESC LIMIT %s",
                    (campaign_id, vehicle_id, limit),
                )
            elif campaign_id is not None:
                cur.execute(
                    "SELECT campaign_id, vehicle_id, data_type, username, row_count, source_info, ts "
                    "FROM ingestion_log WHERE campaign_id=%s ORDER BY ts DESC LIMIT %s",
                    (campaign_id, limit),
                )
            else:
                cur.execute(
                    "SELECT campaign_id, vehicle_id, data_type, username, row_count, source_info, ts "
                    "FROM ingestion_log ORDER BY ts DESC LIMIT %s",
                    (limit,),
                )
            rows = cur.fetchall()
    return [
        {"campaign_id": r[0], "vehicle_id": r[1], "data_type": r[2],
         "username": r[3], "row_count": r[4], "source_info": r[5], "ts": r[6]}
        for r in rows
    ]


def logout() -> None:
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    st.rerun()


# ── Campaign Sheets Config ────────────────────────────────────────────────────
def save_campaign_sheets_config(
    sheet_url: str,
    sheet_name: str = "",
    col_cliente: str = "",
    col_campanha: str = "",
    col_inicio: str = "",
    col_fim: str = "",
    col_veiculos: str = "",
    col_link_plano: str = "",
    col_link_dash: str = "",
    header_row: int = 1,
) -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            # Keep only 1 row (singleton config)
            cur.execute("DELETE FROM campaign_sheets_config")
            cur.execute(
                "INSERT INTO campaign_sheets_config "
                "(sheet_url, sheet_name, col_cliente, col_campanha, col_inicio, col_fim, col_veiculos, col_link_plano, col_link_dash, header_row) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (sheet_url, sheet_name, col_cliente, col_campanha, col_inicio, col_fim, col_veiculos, col_link_plano, col_link_dash, header_row),
            )
    load_campaign_sheets_config.clear()


@st.cache_data(ttl=120, show_spinner=False)
def load_campaign_sheets_config() -> dict | None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT sheet_url, sheet_name, col_cliente, col_campanha, "
                "col_inicio, col_fim, col_veiculos, col_link_plano, col_link_dash, header_row "
                "FROM campaign_sheets_config LIMIT 1"
            )
            row = cur.fetchone()
    if not row:
        return None
    return {
        "sheet_url": row[0],
        "sheet_name": row[1],
        "col_cliente": row[2],
        "col_campanha": row[3],
        "col_inicio": row[4],
        "col_fim": row[5],
        "col_veiculos": row[6],
        "col_link_plano": row[7],
        "col_link_dash": row[8],
        "header_row": row[9],
    }


# ── Alias mapping ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
def get_alias_mappings() -> list[dict]:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, field, source_term, target_term, created_by, created_at "
                "FROM alias_mapping ORDER BY field, source_term"
            )
            rows = cur.fetchall()
    return [
        {"id": r[0], "field": r[1], "source_term": r[2],
         "target_term": r[3], "created_by": r[4], "created_at": r[5]}
        for r in rows
    ]


def save_alias(field: str, source_term: str, target_term: str, username: str = "") -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO alias_mapping (field, source_term, target_term, created_by)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT (field, source_term) DO UPDATE
                   SET target_term = EXCLUDED.target_term,
                       created_by  = EXCLUDED.created_by,
                       created_at  = NOW()""",
                (field, source_term, target_term, username),
            )
    get_alias_mappings.clear()


def delete_alias(alias_id: int) -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM alias_mapping WHERE id=%s", (alias_id,))
    get_alias_mappings.clear()
