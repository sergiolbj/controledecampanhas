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
                "SELECT username, role, expires_at FROM sessions WHERE token=%s",
                (token,),
            )
            row = cur.fetchone()
    if not row:
        return None
    username, role, expires_at = row
    if datetime.utcnow() > datetime.fromisoformat(expires_at):
        delete_session(token)
        return None
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
                st.session_state.update(
                    logged_in=True, username=user, role=role, _just_logged_in=True
                )
                st.rerun()
            else:
                st.error("Usuário ou senha inválidos.")


_PARQUET_MAGIC = b"\x00PQT\x00"  # prefix that identifies parquet-encoded blobs


def save_ingestion(campaign_id: int, vehicle_id: int, data_type: str,
                   df, mapping: dict, source_info: str = "", config_json: str = "{}") -> None:
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

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO ingestion_cache
                (campaign_id, vehicle_id, data_type, data_blob, mapping_json, updated_at, source_info, config_json)
                VALUES (%s,%s,%s,%s,%s,CURRENT_TIMESTAMP,%s,%s)
                ON CONFLICT (campaign_id, vehicle_id, data_type)
                DO UPDATE SET
                    data_blob = EXCLUDED.data_blob,
                    mapping_json = EXCLUDED.mapping_json,
                    updated_at = CURRENT_TIMESTAMP,
                    source_info = EXCLUDED.source_info,
                    config_json = EXCLUDED.config_json
            """, (campaign_id, vehicle_id, data_type,
                  psycopg2.Binary(blob), json.dumps(mapping, default=str), source_info, config_json))
    st.cache_data.clear()


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
    st.cache_data.clear()


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
def get_campaigns(username: str | None = None, role: str | None = None) -> list[dict]:
    with get_db() as conn:
        with conn.cursor() as cur:
            if role == "admin" or username is None:
                cur.execute(
                    "SELECT id, name, COALESCE(client_name,'') FROM campaigns "
                    "ORDER BY client_name, name"
                )
            else:
                cur.execute("""
                    SELECT c.id, c.name, COALESCE(c.client_name,'')
                    FROM campaigns c
                    WHERE c.client_name = ''
                       OR c.client_name IN (
                           SELECT client_name FROM user_client_access WHERE username = %s
                       )
                    ORDER BY c.client_name, c.name
                """, (username,))
            rows = cur.fetchall()
    return [{"id": r[0], "name": r[1], "client_name": r[2]} for r in rows]


def create_campaign(name: str, client_name: str = "") -> int:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO campaigns (name, client_name) VALUES (%s,%s) RETURNING id",
                (name.strip(), client_name.strip()),
            )
            cid = cur.fetchone()[0]
    st.cache_data.clear()
    return cid


def update_campaign_client(campaign_id: int, client_name: str) -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE campaigns SET client_name=%s WHERE id=%s",
                (client_name.strip(), campaign_id),
            )
    st.cache_data.clear()


@st.cache_data(ttl=60, show_spinner=False)
def get_users() -> list[dict]:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT username, role FROM users ORDER BY username"
            )
            rows = cur.fetchall()
    return [{"username": r[0], "role": r[1]} for r in rows]


def add_user(username: str, password: str, role: str) -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (%s,%s,%s)",
                (username.strip(), _hash(password), role),
            )
    st.cache_data.clear()


def update_user(username: str, new_password: str | None = None, new_role: str | None = None) -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            if new_password:
                cur.execute(
                    "UPDATE users SET password_hash=%s WHERE username=%s",
                    (_hash(new_password), username),
                )
            if new_role:
                cur.execute("UPDATE users SET role=%s WHERE username=%s", (new_role, username))
    st.cache_data.clear()


def delete_user(username: str) -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM users WHERE username=%s", (username,))
    st.cache_data.clear()


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
    st.cache_data.clear()


def delete_client(name: str) -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM clients WHERE name=%s", (name,))
            cur.execute("DELETE FROM user_client_access WHERE client_name=%s", (name,))
            cur.execute("UPDATE campaigns SET client_name='' WHERE client_name=%s", (name,))
            cur.execute("UPDATE mapping_templates SET client_name='' WHERE client_name=%s", (name,))
    st.cache_data.clear()


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
    st.cache_data.clear()


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
    st.cache_data.clear()


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
    st.cache_data.clear()
    return vid


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
    st.cache_data.clear()


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
