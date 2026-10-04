import sqlite3
import pandas as pd

conn = sqlite3.connect("audit_log.db")
for table in ["evaluations", "findings", "policy_violations"]:
  df = pd.read_sql_query(f"SELECT * FROM {table}", conn)
  df.to_csv(f"{table}.csv", index=False)
conn.close()
print("Exported successfully!")