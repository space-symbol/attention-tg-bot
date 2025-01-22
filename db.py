from datetime import datetime
import sqlite3
from dotenv import load_dotenv
import os
    
def adapt_datetime_iso(val: datetime):
    """Adapt datetime.datetime to timezone-naive ISO 8601 date."""
    return val.isoformat()

sqlite3.register_adapter(datetime, adapt_datetime_iso)

DB_NAME = 'bot.db'
ADMIN_TELEGRAM_IDS = [os.getenv('ADMIN_ID')]

class Roles():
    admin = 'admin'
    user = 'user'

def create_connection():
    try:
        return sqlite3.connect(DB_NAME, check_same_thread=False)
    except Exception as e:
        print(e)

def setup_database(conn: sqlite3.Connection | None):
    conn = conn if conn else create_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER UNIQUE NOT NULL,
        full_name TEXT NOT NULL,
        attention_score REAL DEFAULT 1.0,
        group_id INTEGER,
        role TEXT CHECK(role IN ('admin', 'user')) NOT NULL
        )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS groups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        teacher_id INTEGER NOT NULL,
        FOREIGN KEY (teacher_id) REFERENCES users(id)
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS polls (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question TEXT NOT NULL,
        group_id INTEGER NOT NULL,
        expires_at DATETIME NOT NULL,
        is_active BOOLEAN DEFAULT TRUE,
        FOREIGN KEY (group_id) REFERENCES groups(id)
    )
    """)
    # Таблица ответов студентов
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS options (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        poll_id INTEGER NOT NULL,
        value TEXT NOT NULL,
        is_answer BOOLEAN DEFAULT 0,
        FOREIGN KEY (poll_id) REFERENCES polls(id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_options (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        option_id INTEGER NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id),
        FOREIGN KEY (option_id) REFERENCES options(id)
        UNIQUE (user_id, option_id)
    )
    """)

    for telegram_id in ADMIN_TELEGRAM_IDS:
        cursor.execute(
            "INSERT OR IGNORE INTO users (telegram_id, full_name, role) VALUES (?, ?, ?)",
            (telegram_id, "Админ", Roles.admin)
        )
    conn.commit()
