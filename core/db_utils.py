from psycopg2.pool import ThreadedConnectionPool
from datetime import datetime
import psycopg2
from datetime import datetime, timezone
from typing import List

_db_pool = None

def init_db_pool(minconn: int, maxconn: int, dsn: str):
    global _db_pool
    if _db_pool is None:
        _db_pool = ThreadedConnectionPool(minconn, maxconn, dsn=dsn)

def get_conn():
    return _db_pool.getconn()

def release_conn(conn):
    _db_pool.putconn(conn)

def close_pool():
    _db_pool.closeall()

def get_all_users():
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name, last_attendance_time FROM persons;")
            return cur.fetchall()
    finally:
        release_conn(conn)

def get_user_by_id(pid: str):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT name, last_attendance_time FROM persons WHERE id = %s;",
                (pid,)
            )
            row = cur.fetchone()
            return (row[0], row[1]) if row else (None, None)
    finally:
        release_conn(conn)

def update_last_attendance_time(pid: str):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE persons SET last_attendance_time = NOW() WHERE id = %s RETURNING last_attendance_time;",
                (pid,)
            )
            new_ts = cur.fetchone()
            conn.commit()
            return new_ts[0] if new_ts else None
    finally:
        release_conn(conn)

def create_person(person_id: str, name: str, last_attendance: datetime):
    conn = _db_pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO persons (id, name, last_attendance_time)
                VALUES (%s, %s, %s)
                """,
                (person_id, name, last_attendance)
            )
        conn.commit()
    finally:
        _db_pool.putconn(conn)

def log_access(db_conn_str: str,
               person_id: str,
               room_name: str,
               result: str,
               reason: str):
    """
    Zapisuje do tabeli access_log.
    result ∈ {'granted','denied','unknown'}.
    """
    conn = psycopg2.connect(db_conn_str)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO access_log (timestamp, person_id, room_name, result, reason)
        VALUES (now(), %s, %s, %s, %s)
    """, (person_id, room_name, result, reason))
    conn.commit()
    cur.close(); conn.close()

def get_all_rooms(db_conn_str: str) -> List[str]:
    import psycopg2
    conn = psycopg2.connect(db_conn_str)
    cur = conn.cursor()
    cur.execute("SELECT room_name FROM rooms ORDER BY room_name")
    rows = [r[0] for r in cur.fetchall()]
    cur.close()
    conn.close()
    return rows
