from flask import Flask, abort, render_template, request

from db import get_connection


app = Flask(__name__)


def query_all(sql: str, params: tuple = ()):
    with get_connection() as conn:
        return conn.execute(sql, params).fetchall()


def query_one(sql: str, params: tuple = ()):
    with get_connection() as conn:
        return conn.execute(sql, params).fetchone()


@app.route("/")
def home():
    year = int(request.args.get("year", 2026))
    group_filter = request.args.get("group")

    where_group = ""
    params = [year]
    if group_filter:
        where_group = "AND c.group_name = ?"
        params.append(group_filter)

    top_games = query_all(
        f"""
        SELECT g.id, g.title, COUNT(*) AS nomination_count
        FROM nominations n
        JOIN categories c ON c.id = n.category_id
        JOIN games g ON g.id = n.game_id
        WHERE n.year = ? {where_group}
        GROUP BY g.id, g.title
        ORDER BY nomination_count DESC, g.title
        LIMIT 12
        """,
        tuple(params),
    )

    groups = query_all("SELECT DISTINCT group_name FROM categories ORDER BY group_name")

    global_stats = query_one(
        """
        SELECT
          (SELECT COUNT(*) FROM games) AS game_count,
          (SELECT COUNT(*) FROM studios) AS studio_count,
          (SELECT COUNT(*) FROM people) AS people_count,
          (SELECT COUNT(*) FROM nominations WHERE year = ?) AS nomination_count
        """,
        (year,),
    )
    return render_template(
        "home.html",
        top_games=top_games,
        groups=groups,
        current_group=group_filter,
        year=year,
        global_stats=global_stats,
    )


@app.route("/games")
def games():
    q = request.args.get("q", "").strip()
    if q:
        rows = query_all(
            """
            SELECT g.*, s.name AS studio_name
            FROM games g
            LEFT JOIN studios s ON s.id = g.studio_id
            WHERE g.title LIKE ?
            ORDER BY g.title
            """,
            (f"%{q}%",),
        )
    else:
        rows = query_all(
            """
            SELECT g.*, s.name AS studio_name
            FROM games g
            LEFT JOIN studios s ON s.id = g.studio_id
            ORDER BY g.title
            """
        )
    return render_template("games.html", games=rows, q=q)


@app.route("/games/<int:game_id>")
def game_detail(game_id: int):
    game = query_one(
        """
        SELECT g.*, s.name AS studio_name, s.id AS studio_id
        FROM games g
        LEFT JOIN studios s ON s.id = g.studio_id
        WHERE g.id = ?
        """,
        (game_id,),
    )
    if not game:
        abort(404)

    nominations = query_all(
        """
        SELECT c.group_name, c.name
        FROM nominations n
        JOIN categories c ON c.id = n.category_id
        WHERE n.game_id = ?
        ORDER BY c.group_name, c.name
        """,
        (game_id,),
    )
    return render_template("game_detail.html", game=game, nominations=nominations)


@app.route("/studios")
def studios():
    q = request.args.get("q", "").strip()
    if q:
        rows = query_all(
            """
            SELECT s.*,
                (SELECT COUNT(*) FROM games g WHERE g.studio_id = s.id) AS game_count
            FROM studios s
            WHERE s.name LIKE ?
            ORDER BY game_count DESC, s.name
            """,
            (f"%{q}%",),
        )
    else:
        rows = query_all(
            """
            SELECT s.*,
                (SELECT COUNT(*) FROM games g WHERE g.studio_id = s.id) AS game_count
            FROM studios s
            ORDER BY game_count DESC, s.name
            """
        )
    return render_template("studios.html", studios=rows, q=q)


@app.route("/studios/<int:studio_id>")
def studio_detail(studio_id: int):
    studio = query_one("SELECT * FROM studios WHERE id = ?", (studio_id,))
    if not studio:
        abort(404)

    games = query_all(
        """
        SELECT g.id, g.title, g.metacritic_score
        FROM games g
        WHERE g.studio_id = ?
        ORDER BY g.title
        """,
        (studio_id,),
    )
    return render_template("studio_detail.html", studio=studio, games=games)


@app.route("/stats")
def stats():
    categories = query_all(
        """
        SELECT
          c.name,
          c.group_name,
          c.nominee_type,
          CASE
            WHEN c.nominee_type = 'person' THEN (
              SELECT COUNT(*) FROM person_nominations pn WHERE pn.category_id = c.id
            )
            ELSE (
              SELECT COUNT(*) FROM nominations n WHERE n.category_id = c.id
            )
          END AS nominee_count
        FROM categories c
        ORDER BY c.group_name, c.name
        """
    )

    top_games = query_all(
        """
        SELECT g.id, g.title, COUNT(*) AS nomination_count
        FROM nominations n
        JOIN games g ON g.id = n.game_id
        GROUP BY g.id, g.title
        ORDER BY nomination_count DESC, g.title
        LIMIT 20
        """
    )

    return render_template("stats.html", categories=categories, top_games=top_games)


if __name__ == "__main__":
    app.run(debug=True)
