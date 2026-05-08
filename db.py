import sqlite3
from contextlib import contextmanager
from pathlib import Path


DB_PATH = Path(__file__).parent / "awards.db"


@contextmanager
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS games (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL UNIQUE,
    description TEXT,
    release_year INTEGER,
    studio_id INTEGER,
    metacritic_score INTEGER,
    metacritic_url TEXT,
    youtube_trailer_url TEXT,
    cover_image_url TEXT,
    official_site_url TEXT,
    wikipedia_url TEXT,
    FOREIGN KEY (studio_id) REFERENCES studios(id)
);

CREATE TABLE IF NOT EXISTS studios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    country TEXT,
    description TEXT,
    logo_image_url TEXT,
    website_url TEXT,
    wikipedia_url TEXT
);

CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    group_name TEXT NOT NULL,
    sponsor TEXT,
    nominee_type TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS nominations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    year INTEGER NOT NULL,
    category_id INTEGER NOT NULL,
    game_id INTEGER,
    studio_id INTEGER,
    organization_name TEXT,
    event_name TEXT,
    is_winner INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (category_id) REFERENCES categories(id),
    FOREIGN KEY (game_id) REFERENCES games(id),
    FOREIGN KEY (studio_id) REFERENCES studios(id),
    UNIQUE(year, category_id, game_id, studio_id, organization_name, event_name)
);

CREATE TABLE IF NOT EXISTS people (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    display_name TEXT NOT NULL UNIQUE,
    person_type TEXT,
    country TEXT,
    bio TEXT,
    social_url TEXT
);

CREATE TABLE IF NOT EXISTS person_nominations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    year INTEGER NOT NULL,
    category_id INTEGER NOT NULL,
    person_id INTEGER NOT NULL,
    game_id INTEGER,
    is_winner INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (category_id) REFERENCES categories(id),
    FOREIGN KEY (person_id) REFERENCES people(id),
    FOREIGN KEY (game_id) REFERENCES games(id),
    UNIQUE(year, category_id, person_id, game_id)
);
"""


def init_db():
    with get_connection() as conn:
        conn.executescript(SCHEMA_SQL)
        _ensure_column(conn, "games", "cover_image_url", "TEXT")
        _ensure_column(conn, "studios", "logo_image_url", "TEXT")


def _ensure_column(conn, table_name: str, column_name: str, column_type: str):
    columns = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    existing = {row["name"] for row in columns}
    if column_name not in existing:
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")


if __name__ == "__main__":
    init_db()
    print(f"Base initialisee: {DB_PATH}")
