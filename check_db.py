import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "audit_log.db")

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

print("=== جدول Evaluations ===")
cursor.execute("SELECT id, timestamp, decision, risk_level, num_findings FROM evaluations")
for row in cursor.fetchall():
    print(row)

print("\n=== جدول Findings ===")
cursor.execute("SELECT evaluation_id, category, severity, likelihood, impact, risk_score FROM findings")
for row in cursor.fetchall():
    print(row)

conn.close()