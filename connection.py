"""
Snowflake connection helper.

Authenticates with a Programmatic Access Token (SNOWFLAKE_PAT) - the method
Personio's team advised for this environment, and the only one this code
supports. See the README's Status section for how the PAT was set up and
a network-policy issue that came up along the way.
"""

import os
import snowflake.connector
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"), override=True)

_connection: snowflake.connector.SnowflakeConnection | None = None
# Reused across calls - a flow like "prep me for X" fires 5-6 queries back to
# back, and re-authenticating with Snowflake on every single one adds seconds
# of avoidable latency for someone prepping under time pressure.


def _new_connection() -> snowflake.connector.SnowflakeConnection:
    required = ["SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "SNOWFLAKE_WAREHOUSE", "SNOWFLAKE_DATABASE", "SNOWFLAKE_PAT"]
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        raise RuntimeError(f"Missing env vars: {missing}")

    return snowflake.connector.connect(
        account=os.getenv("SNOWFLAKE_ACCOUNT"),
        user=os.getenv("SNOWFLAKE_USER"),
        warehouse=os.getenv("SNOWFLAKE_WAREHOUSE"),
        database=os.getenv("SNOWFLAKE_DATABASE"),
        schema=os.getenv("SNOWFLAKE_SCHEMA"),
        role=os.getenv("SNOWFLAKE_ROLE"),
        token=os.getenv("SNOWFLAKE_PAT"),
        authenticator="PROGRAMMATIC_ACCESS_TOKEN",
    )


def get_connection() -> snowflake.connector.SnowflakeConnection:
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
