import sqlite3
from datetime import date, timedelta
from functools import wraps
from flask import (Flask, g, render_template, request, redirect,
                   url_for, session, flash)
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "change-this-secret-key"
DB = "library.db"
LOAN_DAYS = 14
FINE_PER_DAY = 2.0  # currency units per overdue day


# ---------- database helpers ----------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_):
    db = g.pop("db", None)
    if db:
        db.close()


def init_db():
    db = sqlite3.connect(DB)
    with open("schema.sql") as f:
        db.executescript(f.read())
    if not db.execute("SELECT 1 FROM users").fetchone():
        db.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)",
                   ("admin", generate_password_hash("admin123")))
    db.commit()
    db.close()


def login_required(view):
    @wraps(view)
    def wrapped(*a, **kw):
        if "user" not in session:
            return redirect(url_for("login"))
        return view(*a, **kw)
    return wrapped


# ---------- auth ----------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = get_db().execute("SELECT * FROM users WHERE username = ?",
                             (request.form["username"],)).fetchone()
        if u and check_password_hash(u["password_hash"], request.form["password"]):
            session["user"] = u["username"]
            return redirect(url_for("dashboard"))
        flash("Wrong username or password.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------- dashboard ----------
@app.route("/")
@login_required
def dashboard():
    db = get_db()
    today = date.today().isoformat()
    stats = {
        "titles": db.execute("SELECT COUNT(*) FROM books").fetchone()[0],
        "members": db.execute("SELECT COUNT(*) FROM members").fetchone()[0],
        "out": db.execute("SELECT COUNT(*) FROM loans WHERE returned IS NULL").fetchone()[0],
        "overdue": db.execute("SELECT COUNT(*) FROM loans WHERE returned IS NULL AND due < ?",
                              (today,)).fetchone()[0],
    }
    overdue = db.execute("""SELECT loans.*, books.title, members.name FROM loans
        JOIN books ON books.id = book_id JOIN members ON members.id = member_id
        WHERE returned IS NULL AND due < ? ORDER BY due""", (today,)).fetchall()
    return render_template("dashboard.html", stats=stats, overdue=overdue)


# ---------- books ----------
@app.route("/books")
@login_required
def books():
    q = request.args.get("q", "").strip()
    like = f"%{q}%"
    rows = get_db().execute(
        "SELECT * FROM books WHERE title LIKE ? OR author LIKE ? OR isbn LIKE ? OR category LIKE ? ORDER BY title",
        (like, like, like, like)).fetchall()
    return render_template("books.html", books=rows, q=q)


@app.route("/books/add", methods=["GET", "POST"])
@login_required
def add_book():
    if request.method == "POST":
        f = request.form
        copies = max(1, int(f.get("copies") or 1))
        db = get_db()
        db.execute("INSERT INTO books (title, author, isbn, category, copies, available) VALUES (?,?,?,?,?,?)",
                   (f["title"], f["author"], f["isbn"], f["category"], copies, copies))
        db.commit()
        flash("Book added.", "ok")
        return redirect(url_for("books"))
    return render_template("book_form.html", book=None)


@app.route("/books/<int:id>/edit", methods=["GET", "POST"])
@login_required
def edit_book(id):
    db = get_db()
    book = db.execute("SELECT * FROM books WHERE id = ?", (id,)).fetchone()
    if not book:
        return redirect(url_for("books"))
    if request.method == "POST":
        f = request.form
        copies = max(1, int(f.get("copies") or 1))
        out = book["copies"] - book["available"]
        if copies < out:
            flash(f"{out} copies are on loan; copies can't go below that.", "error")
            return render_template("book_form.html", book=book)
        db.execute("UPDATE books SET title=?, author=?, isbn=?, category=?, copies=?, available=? WHERE id=?",
                   (f["title"], f["author"], f["isbn"], f["category"], copies, copies - out, id))
        db.commit()
        flash("Book updated.", "ok")
        return redirect(url_for("books"))
    return render_template("book_form.html", book=book)


@app.route("/books/<int:id>/delete", methods=["POST"])
@login_required
def delete_book(id):
    db = get_db()
    if db.execute("SELECT 1 FROM loans WHERE book_id=?", (id,)).fetchone():
        flash("This book has loan history and can't be deleted.", "error")
    else:
        db.execute("DELETE FROM books WHERE id=?", (id,))
        db.commit()
        flash("Book deleted.", "ok")
    return redirect(url_for("books"))


# ---------- members ----------
@app.route("/members")
@login_required
def members():
    q = request.args.get("q", "").strip()
    like = f"%{q}%"
    rows = get_db().execute("""SELECT members.*,
        (SELECT COUNT(*) FROM loans WHERE member_id = members.id AND returned IS NULL) AS active
        FROM members WHERE name LIKE ? OR email LIKE ? OR phone LIKE ? ORDER BY name""",
        (like, like, like)).fetchall()
    return render_template("members.html", members=rows, q=q)


@app.route("/members/add", methods=["GET", "POST"])
@login_required
def add_member():
    if request.method == "POST":
        f = request.form
        db = get_db()
        db.execute("INSERT INTO members (name, email, phone) VALUES (?,?,?)",
                   (f["name"], f["email"], f["phone"]))
        db.commit()
        flash("Member added.", "ok")
        return redirect(url_for("members"))
    return render_template("member_form.html", member=None)


@app.route("/members/<int:id>/edit", methods=["GET", "POST"])
@login_required
def edit_member(id):
    db = get_db()
    m = db.execute("SELECT * FROM members WHERE id=?", (id,)).fetchone()
    if not m:
        return redirect(url_for("members"))
    if request.method == "POST":
        f = request.form
        db.execute("UPDATE members SET name=?, email=?, phone=? WHERE id=?",
                   (f["name"], f["email"], f["phone"], id))
        db.commit()
        flash("Member updated.", "ok")
        return redirect(url_for("members"))
    return render_template("member_form.html", member=m)


@app.route("/members/<int:id>/delete", methods=["POST"])
@login_required
def delete_member(id):
    db = get_db()
    if db.execute("SELECT 1 FROM loans WHERE member_id=?", (id,)).fetchone():
        flash("This member has loan history and can't be deleted.", "error")
    else:
        db.execute("DELETE FROM members WHERE id=?", (id,))
        db.commit()
        flash("Member deleted.", "ok")
    return redirect(url_for("members"))


# ---------- loans ----------
@app.route("/loans")
@login_required
def loans():
    db = get_db()
    show = request.args.get("show", "active")
    where = "WHERE returned IS NULL" if show == "active" else ""
    rows = db.execute(f"""SELECT loans.*, books.title, members.name FROM loans
        JOIN books ON books.id = book_id JOIN members ON members.id = member_id
        {where} ORDER BY issued DESC, loans.id DESC""").fetchall()
    return render_template("loans.html", loans=rows, show=show,
                           today=date.today().isoformat(), fine_rate=FINE_PER_DAY)


@app.route("/loans/issue", methods=["GET", "POST"])
@login_required
def issue():
    db = get_db()
    if request.method == "POST":
        book_id, member_id = int(request.form["book_id"]), int(request.form["member_id"])
        book = db.execute("SELECT * FROM books WHERE id=?", (book_id,)).fetchone()
        if not book or book["available"] < 1:
            flash("No copies of that book are available.", "error")
        else:
            today = date.today()
            db.execute("INSERT INTO loans (book_id, member_id, issued, due) VALUES (?,?,?,?)",
                       (book_id, member_id, today.isoformat(),
                        (today + timedelta(days=LOAN_DAYS)).isoformat()))
            db.execute("UPDATE books SET available = available - 1 WHERE id=?", (book_id,))
            db.commit()
            flash(f"Book issued. Due in {LOAN_DAYS} days.", "ok")
            return redirect(url_for("loans"))
    books_ = db.execute("SELECT * FROM books WHERE available > 0 ORDER BY title").fetchall()
    members_ = db.execute("SELECT * FROM members ORDER BY name").fetchall()
    return render_template("issue.html", books=books_, members=members_)


@app.route("/loans/<int:id>/return", methods=["POST"])
@login_required
def return_book(id):
    db = get_db()
    loan = db.execute("SELECT * FROM loans WHERE id=? AND returned IS NULL", (id,)).fetchone()
    if loan:
        today = date.today()
        late = (today - date.fromisoformat(loan["due"])).days
        fine = max(0, late) * FINE_PER_DAY
        db.execute("UPDATE loans SET returned=?, fine=? WHERE id=?", (today.isoformat(), fine, id))
        db.execute("UPDATE books SET available = available + 1 WHERE id=?", (loan["book_id"],))
        db.commit()
        flash(f"Returned. Fine: {fine:.2f}" if fine else "Returned. No fine.", "ok")
    return redirect(url_for("loans"))


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
