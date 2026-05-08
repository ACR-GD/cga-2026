from db import get_connection


def print_block(title: str):
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def fetch_scalar(conn, query: str):
    return conn.execute(query).fetchone()[0]


def list_missing(conn, table: str, label_col: str, field: str, limit: int = 20):
    rows = conn.execute(
        f"""
        SELECT {label_col}
        FROM {table}
        WHERE {field} IS NULL OR TRIM({field}) = ''
        ORDER BY {label_col}
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [r[0] for r in rows]


def main():
    with get_connection() as conn:
        games_total = fetch_scalar(conn, "SELECT COUNT(*) FROM games")
        studios_total = fetch_scalar(conn, "SELECT COUNT(*) FROM studios")

        games_with_description = fetch_scalar(
            conn,
            "SELECT COUNT(*) FROM games WHERE description IS NOT NULL AND TRIM(description) <> ''",
        )
        games_with_cover = fetch_scalar(
            conn,
            "SELECT COUNT(*) FROM games WHERE cover_image_url IS NOT NULL AND TRIM(cover_image_url) <> ''",
        )
        games_with_trailer = fetch_scalar(
            conn,
            "SELECT COUNT(*) FROM games WHERE youtube_trailer_url IS NOT NULL AND TRIM(youtube_trailer_url) <> ''",
        )
        games_with_metacritic = fetch_scalar(
            conn,
            "SELECT COUNT(*) FROM games WHERE metacritic_url IS NOT NULL AND TRIM(metacritic_url) <> ''",
        )

        studios_with_description = fetch_scalar(
            conn,
            "SELECT COUNT(*) FROM studios WHERE description IS NOT NULL AND TRIM(description) <> ''",
        )
        studios_with_logo = fetch_scalar(
            conn,
            "SELECT COUNT(*) FROM studios WHERE logo_image_url IS NOT NULL AND TRIM(logo_image_url) <> ''",
        )
        studios_with_website = fetch_scalar(
            conn,
            "SELECT COUNT(*) FROM studios WHERE website_url IS NOT NULL AND TRIM(website_url) <> ''",
        )

        print_block("Couverture globale")
        print(f"Jeux: {games_total}")
        print(f"Studios: {studios_total}")

        print_block("Jeux - couverture des champs")
        print(f"Description: {games_with_description}/{games_total}")
        print(f"Illustration (cover): {games_with_cover}/{games_total}")
        print(f"Trailer YouTube: {games_with_trailer}/{games_total}")
        print(f"Metacritic URL: {games_with_metacritic}/{games_total}")

        print_block("Studios - couverture des champs")
        print(f"Description: {studios_with_description}/{studios_total}")
        print(f"Logo: {studios_with_logo}/{studios_total}")
        print(f"Website: {studios_with_website}/{studios_total}")

        missing_game_covers = list_missing(conn, "games", "title", "cover_image_url")
        missing_game_desc = list_missing(conn, "games", "title", "description")
        missing_studio_logos = list_missing(conn, "studios", "name", "logo_image_url")
        missing_studio_desc = list_missing(conn, "studios", "name", "description")

        print_block("Priorites - manquants (top 20)")
        print("Jeux sans cover:")
        for item in missing_game_covers:
            print(f"- {item}")

        print("\nJeux sans description:")
        for item in missing_game_desc:
            print(f"- {item}")

        print("\nStudios sans logo:")
        for item in missing_studio_logos:
            print(f"- {item}")

        print("\nStudios sans description:")
        for item in missing_studio_desc:
            print(f"- {item}")


if __name__ == "__main__":
    main()
