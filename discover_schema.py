"""
Run this before writing ANY query tools or trusting any schema
description an AI tool generated for you.

It discovers what's REALLY in the PERSONIO database:
- every schema (don't assume CRM/PRODUCT/SUPPORT exist - verify it)
- every table in each schema
- every column and its type
- a few sample rows so you see real data shapes
- row counts

Save the full output - you'll need it to design your tool functions.
"""

import os

from dotenv import load_dotenv

from connection import run_query

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"), override=True)

DATABASE = os.getenv("SNOWFLAKE_DATABASE", "PERSONIO")


def discover():
    print(f"Discovering schemas in {DATABASE} database...\n")
    schemas = run_query(f"SHOW SCHEMAS IN DATABASE {DATABASE}")
    schema_names = [s["name"] for s in schemas if s["name"] not in ("INFORMATION_SCHEMA",)]
    print(f"Found schemas: {schema_names}\n")
    print("=" * 70)

    for schema in schema_names:
        print(f"\nSCHEMA: {schema}")
        print("-" * 70)

        try:
            tables = run_query(f"SHOW TABLES IN SCHEMA {DATABASE}.{schema}")
        except Exception as e:
            print(f"  Could not list tables (permissions?): {e}")
            continue

        table_names = [t["name"] for t in tables]
        if not table_names:
            print("  (no tables found)")
            continue

        for name in table_names:
            print(f"\n  TABLE: {schema}.{name}")
            try:
                columns = run_query(f"DESCRIBE TABLE {DATABASE}.{schema}.{name}")
                for col in columns:
                    print(f"    {col['name']:<30} {col['type']}")

                count = run_query(f"SELECT COUNT(*) AS n FROM {DATABASE}.{schema}.{name}")
                print(f"    Row count: {count[0]['N']}")

                sample = run_query(f"SELECT * FROM {DATABASE}.{schema}.{name} LIMIT 2")
                print(f"    Sample row: {sample[0] if sample else '(empty table)'}")
            except Exception as e:
                print(f"    Error inspecting table: {e}")

        print("\n" + "=" * 70)


if __name__ == "__main__":
    discover()
