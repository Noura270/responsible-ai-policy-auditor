import sqlite3
import os
import pandas as pd
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "audit_log.db")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS evaluations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            mode TEXT,
            content_type TEXT,
            reason TEXT,
            language TEXT,
            decision TEXT,
            risk_level TEXT,
            num_findings INTEGER
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS findings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            evaluation_id INTEGER NOT NULL,
            category TEXT,
            severity TEXT,
            likelihood INTEGER,
            impact INTEGER,
            risk_score INTEGER,
            has_controls INTEGER,
            justification TEXT,
            recommendation TEXT,
            FOREIGN KEY (evaluation_id) REFERENCES evaluations(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS policy_violations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            finding_id INTEGER NOT NULL,
            policy TEXT,
            source TEXT,
            page INTEGER,
            status TEXT,
            evidence TEXT,
            FOREIGN KEY (finding_id) REFERENCES findings(id)
        )
    """)

    conn.commit()
    conn.close()


def log_evaluation(result, mode="content", content_type="", reason="", language="Arabic"):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    timestamp = datetime.now().isoformat(timespec="seconds")
    findings = result.get("findings", [])

    cursor.execute(
        "INSERT INTO evaluations (timestamp, mode, content_type, reason, language, decision, risk_level, num_findings) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            timestamp,
            mode,
            content_type,
            reason,
            language,
            result.get("decision", ""),
            result.get("risk_level", ""),
            len(findings)
        )
    )

    evaluation_id = cursor.lastrowid

    for finding in findings:
        cursor.execute(
            "INSERT INTO findings (evaluation_id, category, severity, likelihood, impact, risk_score, has_controls, justification, recommendation) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                evaluation_id,
                finding.get("category", ""),
                finding.get("severity", ""),
                finding.get("likelihood"),
                finding.get("impact"),
                finding.get("risk_score"),
                1 if finding.get("has_controls") else 0,
                finding.get("justification", ""),
                finding.get("recommendation", "")
            )
        )

        finding_id = cursor.lastrowid

        for violation in finding.get("policy_violations", []):
            cursor.execute(
                "INSERT INTO policy_violations (finding_id, policy, source, page, status, evidence) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    finding_id,
                    violation.get("policy", ""),
                    violation.get("source", ""),
                    violation.get("page"),
                    violation.get("compliance_status", ""),
                    " | ".join(violation.get("evidence", []))
                )
            )

    conn.commit()
    conn.close()
    return evaluation_id


def get_dashboard_data():
    conn = sqlite3.connect(DB_PATH)
    evaluations = pd.read_sql_query("SELECT * FROM evaluations", conn)
    findings = pd.read_sql_query("SELECT * FROM findings", conn)
    policy_violations = pd.read_sql_query("SELECT * FROM policy_violations", conn)
    conn.close()
    return evaluations, findings, policy_violations


if __name__ == "__main__":
    init_db()
    print(f"تم إنشاء قاعدة البيانات في: {os.path.abspath(DB_PATH)}")