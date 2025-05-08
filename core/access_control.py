import psycopg2
from datetime import datetime
from typing import Tuple

# poziom od którego pomijamy harmonogram (admin itp.)
ADMIN_LEVEL = 3

def check_access(db_conn_str: str,
                 person_id: str,
                 room_name: str,
                 when: datetime) -> Tuple[bool,str]:
    """
    Zwraca (granted, reason).
    granted = True jeśli dostęp przyznany.
    reason = 'admin', 'poziom za niski', 'poza harmonogramem', 'nieznany user', ...
    """
    conn = psycopg2.connect(db_conn_str)
    cur = conn.cursor()

    # 1) pobierz poziom usera
    cur.execute("SELECT access_level FROM persons WHERE id=%s", (person_id,))
    row = cur.fetchone()
    if not row:
        cur.close(); conn.close()
        return False, "nieznany user"
    level = row[0]

    # 2) jeśli admin (lub >= progu), przyznaj
    if level >= ADMIN_LEVEL:
        cur.close(); conn.close()
        return True, "admin"

    # 3) pobierz min_access_level pokoju
    cur.execute("SELECT min_access_level FROM rooms WHERE room_name=%s", (room_name,))
    room = cur.fetchone()
    if not room:
        cur.close(); conn.close()
        return False, "nieznany pokój"
    min_level = room[0]

    # 4) poziom za niski?
    if level < min_level:
        cur.close(); conn.close()
        return False, "poziom za niski"

    # 5) sprawdź harmonogram
    dow = when.weekday()  # 0=pon,6=niedz
    t = when.time()
    cur.execute("""
        SELECT 1 FROM access_schedule
         WHERE person_id=%s 
           AND room_name=%s
           AND day_of_week=%s
           AND start_time <= %s
           AND end_time   >= %s
        LIMIT 1
    """, (person_id, room_name, dow, t, t))
    ok = cur.fetchone() is not None
    cur.close(); conn.close()

    if ok:
        return True, "w harmonogramie"
    else:
        return False, "poza harmonogramem"
