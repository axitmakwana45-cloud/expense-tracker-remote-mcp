ExpenseTracker MCP Server

A lightweight MCP server built with FastMCP that lets an LLM client (Claude Desktop, Claude Code, etc.) track, query, and summarize personal expenses backed by a local SQLite database.

Features


Add, view, update, delete, and search expense entries
Summarize spending by category, date range, or month
Export expenses to CSV
Input validation for dates and amounts
Zero external services — just a local expenses.db SQLite file


Requirements


Python 3.10+
fastmcp


Installation

bashpip install fastmcp

Clone or copy this repo, then make sure the following files sit in the same directory:

main.py                # the MCP server
category.json          # list of categories (see below)
expenses.db            # auto-created on first run

category.json

Exposed as the expense://categories resource. Create it next to expense_tracker.py:

json{
  "categories": [
    "Food",
    "Travel",
    "Rent",
    "Utilities",
    "Entertainment",
    "Health",
    "Shopping",
    "Other"
  ]
}

Running the server

bashpython main.py

FastMCP runs over stdio by default, ready to be connected to any MCP-compatible client.

Connecting to Claude Desktop

Add this to your claude_desktop_config.json:

json{
  "mcpServers": {
    "expense-tracker": {
      "command": "python",
      "args": ["/absolute/path/to/main.py"]
    }
  }
}

Restart Claude Desktop and the tools below will be available in chat.

Tools

ToolDescriptionadd_expense(date, amount, category, subcategory="", note="")Add a new expense entry. date must be YYYY-MM-DD.get_expense(expense_id)Fetch a single expense by id.update_expense(expense_id, date=None, amount=None, category=None, subcategory=None, note=None)Update one or more fields of an existing entry. Only provided fields change.delete_expense(expense_id)Delete an entry by id.list_expenses(start_date, end_date, category=None)List entries in an inclusive date range, optionally filtered by category.search_expenses(keyword, start_date=None, end_date=None)Search notes/category/subcategory for a keyword.summarize(start_date, end_date, category=None)Total + count per category over a date range.total_expenses(start_date, end_date, category=None)Grand total and entry count over a date range.monthly_summary(year, month, category=None)Category breakdown for a given calendar month.list_categories()Distinct categories currently present in the data.export_csv(start_date, end_date)Return a CSV string of all entries in the range.

Resources

ResourceDescriptionexpense://categoriesReturns the contents of category.json (read fresh on every access).

Example usage (in chat)

"Add an expense of 933 for travel today"
"Show me all expenses from last week"
"How much did I spend on Food in July 2026?"
"Update expense #4, change the amount to 500"
"Export all June expenses as CSV"

Database schema

sqlCREATE TABLE expenses(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    amount REAL NOT NULL,
    category TEXT NOT NULL,
    subcategory TEXT DEFAULT '',
    note TEXT DEFAULT ''
);

Indexes are created automatically on date and category for faster range queries.

Validation rules


Date: must match YYYY-MM-DD, or the call raises a ValueError.
Amount: must be a positive number.
Category: required and cannot be empty on add_expense.
