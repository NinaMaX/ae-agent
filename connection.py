"""
Snowflake connection helper.
Loads credentials from .env — standard username/password auth.
"""

import os
import snowflake.connector
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"), override=True)

_connection = None  # reused across calls - a call flow like "prep me for X"
                     # fires 5-6 queries back to back, and re-authenticating
                     # with Snowflake on every single one adds seconds of
                     # avoidable latency for someone prepping under time pressure.


def _new_connection():
    required = [
        "SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "SNOWFLAKE_PASSWORD",
        "SNOWFLAKE_WAREHOUSE", "SNOWFLAKE_DATABASE",
    ]
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        raise RuntimeError(f"Missing env vars: {missing}")

    return snowflake.connector.connect(
        account=os.getenv("SNOWFLAKE_ACCOUNT"),
        user=os.getenv("SNOWFLAKE_USER"),
        password=os.getenv("SNOWFLAKE_PASSWORD"),
        warehouse=os.getenv("SNOWFLAKE_WAREHOUSE"),
        database=os.getenv("SNOWFLAKE_DATABASE"),
        schema=os.getenv("SNOWFLAKE_SCHEMA"),
        role=os.getenv("SNOWFLAKE_ROLE"),
    )


def get_connection():
    global _connection
    if _connection is not None and not _connection.is_closed():
        return _connection
    _connection = _new_connection()
    return _connection


def run_query(sql: str, params: tuple = None) -> list[dict]:
    conn = get_connection()
    cur = conn.cursor(snowflake.connector.DictCursor)
    cur.execute(sql, params or ())
    return cur.fetchall()


if __name__ == "__main__":
    result = run_query("SELECT CURRENT_VERSION() AS version")
    print("Connected successfully. Snowflake version:", result[0]["VERSION"])
