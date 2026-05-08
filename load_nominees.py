import json
from pathlib import Path
from typing import Optional

from db import get_connection, init_db


DATA_PATH = Path(__file__).parent / "data" / "nominees_2026.json"
GAME_STUDIO_PATH = Path(__file__).parent / "data" / "game_studio_map.json"


def upsert_game(conn, title: str) -> int:
    conn.execute("INSERT OR IGNORE INTO games(title) VALUES (?)", (title,))
    row = conn.execute("SELECT id FROM games WHERE title = ?", (title,)).fetchone()
    return row["id"]


def upsert_studio(conn, name: str) -> int:
    conn.execute("INSERT OR IGNORE INTO studios(name) VALUES (?)", (name,))
    row = conn.execute("SELECT id FROM studios WHERE name = ?", (name,)).fetchone()
    return row["id"]


def upsert_category(conn, name: str, group_name: str, sponsor: Optional[str], nominee_type: str) -> int:
    conn.execute(
        """
        INSERT INTO categories(name, group_name, sponsor, nominee_type)
        VALUES (?, ?, ?, ?)
        """,
        (name, group_name, sponsor, nominee_type),
    )
    return conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]


def upsert_person(conn, display_name: str, person_type: Optional[str]) -> int:
    conn.execute(
        "INSERT OR IGNORE INTO people(display_name, person_type) VALUES (?, ?)",
        (display_name, person_type),
    )
    row = conn.execute("SELECT id FROM people WHERE display_name = ?", (display_name,)).fetchone()
    return row["id"]


def load_data():
    init_db()
    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    game_studio_map = json.loads(GAME_STUDIO_PATH.read_text(encoding="utf-8"))
    year = payload["year"]

    with get_connection() as conn:
        conn.execute("DELETE FROM person_nominations WHERE year = ?", (year,))
        conn.execute("DELETE FROM nominations WHERE year = ?", (year,))
        conn.execute("DELETE FROM categories")

        for group in payload["award_groups"]:
            group_name = group["name"]
            for category in group["categories"]:
                category_id = upsert_category(
                    conn,
                    category["name"],
                    group_name,
                    category.get("sponsor"),
                    category["nominee_type"],
                )

                nominee_type = category["nominee_type"]
                for nominee in category["nominees"]:
                    if nominee_type == "game":
                        game_id = upsert_game(conn, nominee)
                        conn.execute(
                            """
                            INSERT OR IGNORE INTO nominations(year, category_id, game_id)
                            VALUES (?, ?, ?)
                            """,
                            (year, category_id, game_id),
                        )
                    elif nominee_type == "studio":
                        studio_id = upsert_studio(conn, nominee)
                        conn.execute(
                            """
                            INSERT OR IGNORE INTO nominations(year, category_id, studio_id)
                            VALUES (?, ?, ?)
                            """,
                            (year, category_id, studio_id),
                        )
                    elif nominee_type == "organization":
                        conn.execute(
                            """
                            INSERT OR IGNORE INTO nominations(year, category_id, organization_name)
                            VALUES (?, ?, ?)
                            """,
                            (year, category_id, nominee),
                        )
                    elif nominee_type == "event":
                        conn.execute(
                            """
                            INSERT OR IGNORE INTO nominations(year, category_id, event_name)
                            VALUES (?, ?, ?)
                            """,
                            (year, category_id, nominee),
                        )
                    elif nominee_type == "person":
                        person_id = upsert_person(conn, nominee["person_name"], nominee.get("person_type"))
                        game_id = None
                        if nominee.get("game"):
                            game_id = upsert_game(conn, nominee["game"])
                        conn.execute(
                            """
                            INSERT OR IGNORE INTO person_nominations(year, category_id, person_id, game_id)
                            VALUES (?, ?, ?, ?)
                            """,
                            (year, category_id, person_id, game_id),
                        )
                    else:
                        raise ValueError(f"Type de nomine non supporte: {nominee_type}")

        for game_title, studio_name in game_studio_map.items():
            game_id = upsert_game(conn, game_title)
            studio_id = upsert_studio(conn, studio_name)
            conn.execute("UPDATE games SET studio_id = ? WHERE id = ?", (studio_id, game_id))

    print("Import termine.")


if __name__ == "__main__":
    load_data()
