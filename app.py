from flask import Flask, render_template, request, redirect, url_for, flash
import re
import sqlite3
from datetime import datetime
from pathlib import Path

app = Flask(__name__)
app.secret_key = "dev-only-change-later"

DB_PATH = Path(__file__).parent / "notes.db"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def pretty_date(value):
    if not value or "T" not in value:
        return value
    try:
        return datetime.fromisoformat(value).strftime("%d %b %Y, %H:%M")
    except ValueError:
        return value


def init_db():
    with get_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT
            )
            """
        )
        cols = [row["name"] for row in conn.execute("PRAGMA table_info(notes)").fetchall()]
        if "updated_at" not in cols:
            conn.execute("ALTER TABLE notes ADD COLUMN updated_at TEXT")

        for row in conn.execute("SELECT id, created_at, updated_at FROM notes").fetchall():
            created = pretty_date(row["created_at"])
            updated = pretty_date(row["updated_at"])
            if created != row["created_at"] or updated != row["updated_at"]:
                conn.execute(
                    "UPDATE notes SET created_at = ?, updated_at = ? WHERE id = ?",
                    (created, updated, row["id"]),
                )


def count_notes():
    with get_db() as conn:
        return conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]


def now_str():
    return datetime.now().strftime("%d %b %Y, %H:%M")


def tokenize_query(q):
    """Split search text on whitespace; drop empty tokens."""
    return [token for token in q.split() if token]


def note_matches_tokens(note, tokens):
    """Require every token as a whole word in title or content (case-insensitive)."""
    haystack = f"{note['title'] or ''} {note['content'] or ''}"
    return all(
        re.search(r"\b" + re.escape(token) + r"\b", haystack, re.IGNORECASE)
        for token in tokens
    )


@app.context_processor
def inject_note_count():
    return {"note_count": count_notes()}


@app.route("/")
def index():
    q = request.args.get("q", "").strip()
    tokens = tokenize_query(q)
    with get_db() as conn:
        if tokens:
            clauses = []
            params = []
            for token in tokens:
                clauses.append("(title LIKE ? OR content LIKE ?)")
                params.extend([f"%{token}%", f"%{token}%"])
            sql = (
                "SELECT * FROM notes WHERE "
                + " AND ".join(clauses)
                + " ORDER BY id DESC"
            )
            candidates = conn.execute(sql, params).fetchall()
            # LIKE alone matches substrings inside longer words (e.g. "jon" in
            # "florjon"); keep only notes where every token is a whole word.
            notes = [note for note in candidates if note_matches_tokens(note, tokens)]
        else:
            notes = conn.execute(
                "SELECT * FROM notes ORDER BY id DESC"
            ).fetchall()
    return render_template("index.html", notes=notes, q=q)


@app.route("/add", methods=["GET", "POST"])
def add():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        content = request.form.get("content", "").strip()
        if not title or not content:
            flash("Title and content cannot be empty.")
            return render_template(
                "form.html", note=None, title=title, content=content
            )
        stamp = now_str()
        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO notes (title, content, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (title, content, stamp, stamp),
            )
        return redirect(url_for("index"))
    return render_template("form.html", note=None)


@app.route("/edit/<int:note_id>", methods=["GET", "POST"])
def edit(note_id):
    with get_db() as conn:
        note = conn.execute(
            "SELECT * FROM notes WHERE id = ?", (note_id,)
        ).fetchone()
    if note is None:
        return redirect(url_for("index"))
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        content = request.form.get("content", "").strip()
        if not title or not content:
            flash("Title and content cannot be empty.")
            return render_template(
                "form.html", note=note, title=title, content=content
            )
        with get_db() as conn:
            conn.execute(
                """
                UPDATE notes
                SET title = ?, content = ?, updated_at = ?
                WHERE id = ?
                """,
                (title, content, now_str(), note_id),
            )
        return redirect(url_for("index"))
    return render_template("form.html", note=note)


@app.route("/delete/<int:note_id>", methods=["POST"])
def delete(note_id):
    with get_db() as conn:
        conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
    return redirect(url_for("index"))


if __name__ == "__main__":
    init_db()
    app.run(debug=True)