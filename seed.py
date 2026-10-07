"""Optional: load sample books and members.  Run: python seed.py"""
import sqlite3
from app import init_db, DB

init_db()
db = sqlite3.connect(DB)
if not db.execute("SELECT 1 FROM books").fetchone():
    db.executemany("INSERT INTO books (title, author, isbn, category, copies, available) VALUES (?,?,?,?,?,?)", [
        ("Wings of Fire", "A. P. J. Abdul Kalam", "9788173711466", "Biography", 3, 3),
        ("The Guide", "R. K. Narayan", "9780143039648", "Fiction", 2, 2),
        ("Ponniyin Selvan", "Kalki Krishnamurthy", "9788184930092", "Historical", 2, 2),
        ("Clean Code", "Robert C. Martin", "9780132350884", "Programming", 1, 1),
        ("Python Crash Course", "Eric Matthes", "9781593279288", "Programming", 2, 2),
    ])
    db.executemany("INSERT INTO members (name, email, phone) VALUES (?,?,?)", [
        ("Priya Raman", "priya@example.com", "9876500001"),
        ("Karthik S", "karthik@example.com", "9876500002"),
    ])
    db.commit()
print("Sample data loaded.")
