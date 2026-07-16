from fastmcp import FastMCP
import os
import sqlite3
import json
import csv
import io
from datetime import datetime
from contextlib import contextmanager
from dotenv import load_dotenv

from fastmcp.server.auth.providers.jwt import StaticTokenVerifier

load_dotenv()

auth = StaticTokenVerifier(
    tokens=[os.getenv("MCP_TOKEN")]
)

mcp = FastMCP(
    "Expense Tracker",
    auth=auth
)

DB_PATH = os.path.join(os.path.dirname(__file__), "expenses.db")
CATEGORIES_PATH = os.path.join(os.path.dirname(__file__), "category.json")

mcp = FastMCP("ExpenseTracker")


# ---------- helpers ----------

@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def rows_to_dicts(rows):
    return [dict(r) for r in rows]


def validate_date(date_str):
    """Ensure date is in YYYY-MM-DD format."""
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        raise ValueError(f"Invalid date '{date_str}'. Expected format: YYYY-MM-DD")


def validate_amount(amount):
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid amount '{amount}'. Must be a number")
    if amount <= 0:
        raise ValueError("Amount must be greater than 0")
    return amount


def init_db():
    with get_conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS expenses(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                amount REAL NOT NULL,
                category TEXT NOT NULL,
                subcategory TEXT DEFAULT '',
                note TEXT DEFAULT ''
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses(date)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_expenses_category ON expenses(category)")


init_db()


# ---------- existing tools (hardened) ----------

@mcp.tool()
def add_expense(date, amount, category, subcategory="", note=""):
    """Add a new expense entry to the database."""
    validate_date(date)
    amount = validate_amount(amount)
    if not category or not str(category).strip():
        raise ValueError("Category is required")

    with get_conn() as c:
        cur = c.execute(
            "INSERT INTO expenses(date, amount, category, subcategory, note) VALUES (?,?,?,?,?)",
            (date, amount, category, subcategory, note)
        )
        return {"status": "ok", "id": cur.lastrowid}


@mcp.tool()
def list_expenses(start_date, end_date, category=None):
    """List expense entries within an inclusive date range, optionally filtered by category."""
    validate_date(start_date)
    validate_date(end_date)

    query = """
        SELECT id, date, amount, category, subcategory, note
        FROM expenses
        WHERE date BETWEEN ? AND ?
    """
    params = [start_date, end_date]

    if category:
        query += " AND category = ?"
        params.append(category)

    query += " ORDER BY date ASC, id ASC"

    with get_conn() as c:
        cur = c.execute(query, params)
        return rows_to_dicts(cur.fetchall())


@mcp.tool()
def summarize(start_date, end_date, category=None):
    """Summarize expenses by category within an inclusive date range."""
    validate_date(start_date)
    validate_date(end_date)

    query = """
        SELECT category, SUM(amount) AS total_amount, COUNT(*) AS entry_count
        FROM expenses
        WHERE date BETWEEN ? AND ?
    """
    params = [start_date, end_date]

    if category:
        query += " AND category = ?"
        params.append(category)

    query += " GROUP BY category ORDER BY category ASC"

    with get_conn() as c:
        cur = c.execute(query, params)
        return rows_to_dicts(cur.fetchall())


# ---------- new tools ----------

@mcp.tool()
def get_expense(expense_id):
    """Fetch a single expense entry by its id."""
    with get_conn() as c:
        cur = c.execute(
            "SELECT id, date, amount, category, subcategory, note FROM expenses WHERE id = ?",
            (expense_id,)
        )
        row = cur.fetchone()
        if row is None:
            raise ValueError(f"No expense found with id {expense_id}")
        return dict(row)


@mcp.tool()
def update_expense(expense_id, date=None, amount=None, category=None, subcategory=None, note=None):
    """Update one or more fields of an existing expense entry. Only provided fields are changed."""
    with get_conn() as c:
        cur = c.execute("SELECT id FROM expenses WHERE id = ?", (expense_id,))
        if cur.fetchone() is None:
            raise ValueError(f"No expense found with id {expense_id}")

        fields = []
        params = []

        if date is not None:
            validate_date(date)
            fields.append("date = ?")
            params.append(date)
        if amount is not None:
            fields.append("amount = ?")
            params.append(validate_amount(amount))
        if category is not None:
            if not str(category).strip():
                raise ValueError("Category cannot be empty")
            fields.append("category = ?")
            params.append(category)
        if subcategory is not None:
            fields.append("subcategory = ?")
            params.append(subcategory)
        if note is not None:
            fields.append("note = ?")
            params.append(note)

        if not fields:
            raise ValueError("No fields provided to update")

        params.append(expense_id)
        c.execute(f"UPDATE expenses SET {', '.join(fields)} WHERE id = ?", params)
        return {"status": "ok", "id": expense_id, "updated_fields": len(fields)}


@mcp.tool()
def delete_expense(expense_id):
    """Delete an expense entry by its id."""
    with get_conn() as c:
        cur = c.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
        if cur.rowcount == 0:
            raise ValueError(f"No expense found with id {expense_id}")
        return {"status": "ok", "deleted_id": expense_id}


@mcp.tool()
def search_expenses(keyword, start_date=None, end_date=None):
    """Search expenses whose note, category, or subcategory contains the given keyword."""
    query = """
        SELECT id, date, amount, category, subcategory, note
        FROM expenses
        WHERE (note LIKE ? OR category LIKE ? OR subcategory LIKE ?)
    """
    like = f"%{keyword}%"
    params = [like, like, like]

    if start_date:
        validate_date(start_date)
        query += " AND date >= ?"
        params.append(start_date)
    if end_date:
        validate_date(end_date)
        query += " AND date <= ?"
        params.append(end_date)

    query += " ORDER BY date ASC, id ASC"

    with get_conn() as c:
        cur = c.execute(query, params)
        return rows_to_dicts(cur.fetchall())


@mcp.tool()
def total_expenses(start_date, end_date, category=None):
    """Return the total amount spent within an inclusive date range, optionally filtered by category."""
    validate_date(start_date)
    validate_date(end_date)

    query = "SELECT SUM(amount) AS total, COUNT(*) AS entry_count FROM expenses WHERE date BETWEEN ? AND ?"
    params = [start_date, end_date]

    if category:
        query += " AND category = ?"
        params.append(category)

    with get_conn() as c:
        cur = c.execute(query, params)
        row = cur.fetchone()
        return {
            "total": row["total"] or 0.0,
            "entry_count": row["entry_count"],
            "start_date": start_date,
            "end_date": end_date,
            "category": category
        }


@mcp.tool()
def monthly_summary(year, month, category=None):
    """Summarize expenses by category for a specific month (year=2026, month=7)."""
    month = int(month)
    year = int(year)
    if not (1 <= month <= 12):
        raise ValueError("Month must be between 1 and 12")

    start_date = f"{year:04d}-{month:02d}-01"
    if month == 12:
        end_date = f"{year + 1:04d}-01-01"
    else:
        end_date = f"{year:04d}-{month + 1:02d}-01"

    query = """
        SELECT category, SUM(amount) AS total_amount, COUNT(*) AS entry_count
        FROM expenses
        WHERE date >= ? AND date < ?
    """
    params = [start_date, end_date]

    if category:
        query += " AND category = ?"
        params.append(category)

    query += " GROUP BY category ORDER BY category ASC"

    with get_conn() as c:
        cur = c.execute(query, params)
        return rows_to_dicts(cur.fetchall())


@mcp.tool()
def list_categories():
    """List all distinct categories currently used in the expenses table."""
    with get_conn() as c:
        cur = c.execute("SELECT DISTINCT category FROM expenses ORDER BY category ASC")
        return [r["category"] for r in cur.fetchall()]


@mcp.tool()
def export_csv(start_date, end_date):
    """Export expenses within an inclusive date range as a CSV-formatted string."""
    validate_date(start_date)
    validate_date(end_date)

    with get_conn() as c:
        cur = c.execute(
            """
            SELECT id, date, amount, category, subcategory, note
            FROM expenses
            WHERE date BETWEEN ? AND ?
            ORDER BY date ASC, id ASC
            """,
            (start_date, end_date)
        )
        rows = cur.fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "date", "amount", "category", "subcategory", "note"])
    for r in rows:
        writer.writerow([r["id"], r["date"], r["amount"], r["category"], r["subcategory"], r["note"]])

    return output.getvalue()


@mcp.resource("expense://categories", mime_type="application/json")
def categories():
    # Read fresh each time so you can edit the file without restarting
    with open(CATEGORIES_PATH, "r", encoding="utf-8") as f:
        return f.read()


if __name__ == "__main__":
    mcp.run(transport='http',host="0.0.0.0",port = 8000)