Relational Scholarship & Student Disbursement Dashboard
Run locally with:
    pip install streamlit pandas
    streamlit run scholarship_dashboard.py

Note: SQLite supplies its own transaction/recovery mechanisms. This project includes
an educational explanation of Shadow Paging and ARIES; it does NOT claim that SQLite
internally implements ARIES or classic Shadow Paging.
"""

import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

DB_PATH = Path(__file__).with_name("scholarship_dashboard.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialize_database():
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS schemes (
                scheme_id INTEGER PRIMARY KEY AUTOINCREMENT,
                scheme_name TEXT NOT NULL UNIQUE,
                coordinator_email TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS applications (
                application_id INTEGER PRIMARY KEY AUTOINCREMENT,
                scheme_id INTEGER NOT NULL,
                student_name TEXT NOT NULL,
                application_date TEXT NOT NULL,
                FOREIGN KEY (scheme_id) REFERENCES schemes(scheme_id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS disbursements (
                disbursement_id INTEGER PRIMARY KEY AUTOINCREMENT,
                application_id INTEGER NOT NULL,
                disbursement_type TEXT NOT NULL,
                disbursed_amount REAL NOT NULL CHECK (disbursed_amount >= 0),
                FOREIGN KEY (application_id) REFERENCES applications(application_id)
                    ON DELETE CASCADE
            );
        """)

        # Seed only when all three tables are completely empty.
        counts = [
            conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("schemes", "applications", "disbursements")
        ]
        if counts == [0, 0, 0]:
            scheme_rows = [
                ("State Merit Scholarship", "merit@example.gov.in"),
                ("Student Support Grant", "support@example.gov.in"),
            ]
            conn.executemany(
                "INSERT INTO schemes (scheme_name, coordinator_email) VALUES (?, ?)",
                scheme_rows,
            )
            scheme_ids = {
                row["scheme_name"]: row["scheme_id"]
                for row in conn.execute("SELECT scheme_id, scheme_name FROM schemes")
            }
            conn.executemany(
                """INSERT INTO applications
                   (scheme_id, student_name, application_date)
                   VALUES (?, ?, ?)""",
                [
                    (scheme_ids["State Merit Scholarship"], "Priya Sharma", "2026-10-10"),
                    (scheme_ids["Student Support Grant"], "Rahul Verma", "2026-10-12"),
                ],
            )
            app_ids = {
                row["student_name"]: row["application_id"]
                for row in conn.execute(
                    "SELECT application_id, student_name FROM applications"
                )
            }
            conn.executemany(
                """INSERT INTO disbursements
                   (application_id, disbursement_type, disbursed_amount)
                   VALUES (?, ?, ?)""",
                [
                    (app_ids["Priya Sharma"], "Tuition Fee Grant", 25000.00),
                    (app_ids["Rahul Verma"], "Book Grant", 3000.00),
                ],
            )


def fetch_df(sql, params=()):
    with get_connection() as conn:
        return pd.read_sql_query(sql, conn, params=params)


def add_record(scheme_name, coordinator_email, student_name, disbursement_type, amount):
    with get_connection() as conn:
        # One atomic transaction: all three inserts succeed, or none do.
        with conn:
            row = conn.execute(
                "SELECT scheme_id FROM schemes WHERE scheme_name = ?",
                (scheme_name,),
            ).fetchone()
            if row:
                scheme_id = row["scheme_id"]
                # Keep existing coordinator details, unless the email was changed.
                conn.execute(
                    "UPDATE schemes SET coordinator_email = ? WHERE scheme_id = ?",
                    (coordinator_email, scheme_id),
                )
            else:
                cursor = conn.execute(
                    "INSERT INTO schemes (scheme_name, coordinator_email) VALUES (?, ?)",
                    (scheme_name, coordinator_email),
                )
                scheme_id = cursor.lastrowid

            cursor = conn.execute(
                """INSERT INTO applications
                   (scheme_id, student_name, application_date)
                   VALUES (?, ?, ?)""",
                (scheme_id, student_name, date.today().isoformat()),
            )
            application_id = cursor.lastrowid

            conn.execute(
                """INSERT INTO disbursements
                   (application_id, disbursement_type, disbursed_amount)
                   VALUES (?, ?, ?)""",
                (application_id, disbursement_type, amount),
            )


def delete_record(kind, record_id):
    sql_by_kind = {
        "scheme": ("DELETE FROM schemes WHERE scheme_id = ?", "Scheme"),
        "application": ("DELETE FROM applications WHERE application_id = ?", "Application"),
        "disbursement": ("DELETE FROM disbursements WHERE disbursement_id = ?", "Disbursement"),
    }
    sql, label = sql_by_kind[kind]
    with get_connection() as conn:
        with conn:
            cur = conn.execute(sql, (record_id,))
            if cur.rowcount == 0:
                raise ValueError(f"{label} no longer exists. Refresh and select again.")


def main():
    st.set_page_config(page_title="Scholarship Disbursement Dashboard",
                       page_icon="🎓", layout="wide")
    initialize_database()

    st.title("🎓 Scholarship & Student Disbursement Dashboard")
    st.caption("SQLite relational database • Foreign-key integrity • Cascading deletes")

    with st.sidebar:
        st.header("Database status")
        scheme_count = fetch_df("SELECT COUNT(*) AS n FROM schemes").iloc[0]["n"]
        app_count = fetch_df("SELECT COUNT(*) AS n FROM applications").iloc[0]["n"]
        disb_count = fetch_df("SELECT COUNT(*) AS n FROM disbursements").iloc[0]["n"]
        st.metric("Schemes", int(scheme_count))
        st.metric("Applications", int(app_count))
        st.metric("Disbursements", int(disb_count))
        st.info(f"Database file: `{DB_PATH.name}`")
        with st.expander("How recovery concepts relate to this project"):
            st.markdown("""
**Shadow Paging:** conceptually preserves an old page-table view while changes
are written to new pages. A commit switches to the new view; a pre-commit crash
keeps the old view.

**ARIES:** a log-based recovery algorithm with Analysis, Redo and Undo phases,
using Write-Ahead Logging and compensation log records.

**Important implementation note:** this application uses SQLite transactions
and SQLite's own recovery mechanisms. It does not implement ARIES or classic
Shadow Paging internally. These algorithms should be explained or simulated
separately in the project report if your instructor specifically requires them.
""")

    insert_tab, delete_tab, display_tab, recovery_tab = st.tabs(
        ["➕ Add Record", "🗑️ Delete Records", "📊 View Tables", "🔄 Recovery Concepts"]
    )

    with insert_tab:
        st.subheader("Insert a scholarship application and its disbursement")
        st.write("One submission creates one application and one disbursement.")
        with st.form("insert_form", clear_on_submit=True):
            scheme_name = st.text_input("Scheme Name", placeholder="State Merit Scholarship")
            email = st.text_input("Scheme Coordinator Email",
                                  placeholder="coordinator@example.gov.in")
            student_name = st.text_input("Student Name", placeholder="Priya Sharma")
            disbursement_type = st.selectbox(
                "Disbursement Type",
                ["Tuition Fee Grant", "Hostel Allowance", "Book Grant", "Other"],
            )
            amount_text = st.text_input("Disbursed Amount (₹)", placeholder="25000")
            submitted = st.form_submit_button("Add Record", type="primary")

        if submitted:
            errors = []
            if not scheme_name.strip():
                errors.append("Scheme name cannot be blank.")
            if not email.strip():
                errors.append("Coordinator email cannot be blank.")
            elif "@" not in email.strip() or "." not in email.strip().split("@")[-1]:
                errors.append("Enter a valid coordinator email address.")
            if not student_name.strip():
                errors.append("Student name cannot be blank.")
            if not disbursement_type.strip():
                errors.append("Disbursement type cannot be blank.")
            try:
                amount = float(amount_text.strip())
                if amount < 0:
                    errors.append("Amount cannot be negative.")
            except (ValueError, AttributeError):
                errors.append("Amount must be a valid non-negative number.")

            if errors:
                for err in errors:
                    st.error(err)
            else:
                try:
                    add_record(scheme_name.strip(), email.strip(), student_name.strip(),
                               disbursement_type, amount)
                    st.success("Application and disbursement added successfully.")
                    st.rerun()
                except sqlite3.IntegrityError as exc:
                    st.error(f"Database integrity error: {exc}")
                except sqlite3.Error as exc:
                    st.error(f"Database error: {exc}")

    with delete_tab:
        st.subheader("Delete a selected record")
        delete_kind = st.radio(
            "Record type",
            ["Scholarship Scheme", "Student Application", "Disbursement"],
            horizontal=True,
        )

        if delete_kind == "Scholarship Scheme":
            records = fetch_df("SELECT scheme_id, scheme_name FROM schemes ORDER BY scheme_name")
            id_col = "scheme_id"
            options = [(int(r[id_col]), f'{r[id_col]} · {r["scheme_name"]}')
                       for _, r in records.iterrows()]
            kind = "scheme"
        elif delete_kind == "Student Application":
            records = fetch_df("""
                SELECT a.application_id, a.student_name, s.scheme_name, a.application_date
                FROM applications a JOIN schemes s ON s.scheme_id = a.scheme_id
                ORDER BY a.application_id
            """)
            id_col = "application_id"
            options = [(int(r[id_col]),
                        f'{r[id_col]} · {r["student_name"]} · {r["scheme_name"]} · {r["application_date"]}')
                       for _, r in records.iterrows()]
            kind = "application"
        else:
            records = fetch_df("""
                SELECT d.disbursement_id, d.disbursement_type, d.disbursed_amount,
                       a.student_name
                FROM disbursements d
                JOIN applications a ON a.application_id = d.application_id
                ORDER BY d.disbursement_id
            """)
            id_col = "disbursement_id"
            options = [(int(r[id_col]),
                        f'{r[id_col]} · {r["student_name"]} · {r["disbursement_type"]} · ₹{r["disbursed_amount"]:.2f}')
                       for _, r in records.iterrows()]
            kind = "disbursement"

        if not options:
            st.info("There are no records of this type to delete.")
        else:
            labels = {record_id: label for record_id, label in options}
            selected_id = st.selectbox(
                "Select record", options=[rid for rid, _ in options],
                format_func=lambda rid: labels.get(rid, f"ID {rid}"),
                key=f"delete_select_{kind}",
            )
            if kind == "scheme":
                st.warning("Deleting a scheme also deletes all its applications and their disbursements.")
            elif kind == "application":
                st.warning("Deleting an application also deletes its disbursements.")
            else:
                st.caption("Only this disbursement will be deleted. Its application and scheme remain.")
            if st.button("Delete Selected", type="primary", key="delete_button"):
                try:
                    delete_record(kind, selected_id)
                    st.success("Selected record deleted.")
                    st.rerun()
                except (sqlite3.Error, ValueError) as exc:
                    st.error(str(exc))
                    st.rerun()

    with display_tab:
        st.subheader("Live database views")
        joined, schemes_view, applications_view, disbursements_view = st.tabs(
            ["Combined JOIN", "Schemes", "Applications", "Disbursements"]
        )
        with joined:
            df = fetch_df("""
                SELECT a.application_id AS "Application ID",
                       s.scheme_name AS "Scheme Name",
                       a.student_name AS "Student Name",
                       a.application_date AS "Application Date",
                       d.disbursement_type AS "Disbursement Type",
                       d.disbursed_amount AS "Disbursed Amount (₹)"
                FROM applications a
                JOIN schemes s ON s.scheme_id = a.scheme_id
                JOIN disbursements d ON d.application_id = a.application_id
                ORDER BY a.application_id, d.disbursement_id
            """)
            st.dataframe(df, use_container_width=True, hide_index=True)
        with schemes_view:
            st.dataframe(fetch_df("SELECT * FROM schemes ORDER BY scheme_id"),
                         use_container_width=True, hide_index=True)
        with applications_view:
            st.dataframe(fetch_df("SELECT * FROM applications ORDER BY application_id"),
                         use_container_width=True, hide_index=True)
        with disbursements_view:
            st.dataframe(fetch_df("SELECT * FROM disbursements ORDER BY disbursement_id"),
                         use_container_width=True, hide_index=True)

    with recovery_tab:
        st.subheader("How recovery applies to this database")
        st.markdown("""
The add operation is enclosed in a single SQLite transaction. If inserting the
application or disbursement fails, the transaction rolls back rather than leaving
a partial submission.

| Failure scenario | Expected safe outcome |
|---|---|
| Crash before a transaction commits | SQLite recovery leaves the transaction uncommitted and rolls it back |
| Crash after commit is durable | The committed records remain |
| Delete a scheme | Foreign-key `ON DELETE CASCADE` removes its applications and disbursements |
| Delete one disbursement | Only that disbursement row is removed |

**For your DBMS report**
- Explain Shadow Paging using old/new page-table diagrams.
- Explain ARIES using Analysis → Redo → Undo and Write-Ahead Logging.
- Distinguish the theory from this app: SQLite provides atomic transactions and crash recovery, but this Python code does not reimplement the internal ARIES or Shadow Paging algorithms.
""")
        if st.button("Check foreign-key enforcement"):
            with get_connection() as conn:
                status = conn.execute("PRAGMA foreign_keys").fetchone()[0]
            if status == 1:
                st.success("Foreign-key enforcement is ON for this connection.")
            else:
                st.error("Foreign-key enforcement is OFF.")

    st.caption("Tip: Use the Delete Records tab to test cascade-delete behavior, then verify the result in all table views.")


if __name__ == "__main__":
    main()
