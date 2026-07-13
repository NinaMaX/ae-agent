"""
Account-data tools backed by live Snowflake queries.

Schema (confirmed via the Database Explorer screenshots — actual provisioned
DB is PERSONIO, not the CASE_STUDY/GTM layout described in the case brief):

  CRM.ACCOUNTS       (75 rows)  ACCOUNT_ID, ARR_EUR, COMPANY_NAME, CREATED_AT,
                                 CUSTOMER_SINCE, EMPLOYEE_COUNT, INDUSTRY,
                                 OWNER_AE, REGION, SEGMENT, STATUS
  CRM.CONTACTS       (299 rows) ACCOUNT_ID, CONTACT_ID, CREATED_AT, EMAIL,
                                 FULL_NAME, LAST_INTERACTION, PERSONA_TYPE,
                                 ROLE_TITLE
  CRM.OPPORTUNITIES  (85 rows)  ACCOUNT_ID, AMOUNT_EUR, CLOSE_DATE,
                                 CREATED_AT, DAYS_IN_STAGE, NAME,
                                 OPPORTUNITY_ID, OWNER_AE, STAGE, TYPE,
                                 WON_LOST_REASON
  CRM.ACTIVITIES     (747 rows) ACCOUNT_ID, ACTIVITY_DATE, ACTIVITY_ID,
                                 ACTIVITY_TYPE, CONTACT_ID, OPPORTUNITY_ID,
                                 OWNER_AE, SUBJECT, SUMMARY
  PRODUCT.USAGE      (246 rows) ACCOUNT_ID, LOGINS, MONTH,
                                 MONTHLY_ACTIVE_USERS, PAYROLL_RUNS,
                                 PERFORMANCE_CYCLES_ACTIVE,
                                 PERFORMANCE_MODULE_ACTIVE,
                                 RECRUITING_MODULE_ACTIVE, USAGE_ID
  SUPPORT.TICKETS    (47 rows)  ACCOUNT_ID, CREATED_DATE, PRIORITY,
                                 RESOLVED_DATE, STATUS, SUBJECT, SUMMARY,
                                 TICKET_ID

We don't know the exact enum values for STAGE / STATUS / PRIORITY yet (no
sample rows pulled — MFA is still blocking a live connection as of writing).
Tools deliberately return raw rows rather than filtering on guessed enum
strings (e.g. STATUS = 'Open') so nothing silently drops data because of a
wrong assumption. Revisit once discover_schema.py has run against live data.
"""

from connection import run_query


def find_account(name_query: str) -> list[dict]:
    """Fuzzy-matches a company name to account records. AEs will type
    approximate names, so this is the entry point for every other tool."""
    return run_query(
        """
        SELECT ACCOUNT_ID, COMPANY_NAME, INDUSTRY, REGION, SEGMENT, STATUS, OWNER_AE
        FROM CRM.ACCOUNTS
        WHERE COMPANY_NAME ILIKE %s
        LIMIT 5
        """,
        (f"%{name_query}%",),
    )


def get_account_summary(account_id: str) -> list[dict]:
    return run_query(
        "SELECT * FROM CRM.ACCOUNTS WHERE ACCOUNT_ID = %s",
        (account_id,),
    )


def get_contacts(account_id: str) -> list[dict]:
    return run_query(
        """
        SELECT FULL_NAME, ROLE_TITLE, PERSONA_TYPE, EMAIL, LAST_INTERACTION
        FROM CRM.CONTACTS
        WHERE ACCOUNT_ID = %s
        ORDER BY LAST_INTERACTION DESC
        """,
        (account_id,),
    )


def get_opportunities(account_id: str) -> list[dict]:
    return run_query(
        """
        SELECT OPPORTUNITY_ID, NAME, TYPE, STAGE, AMOUNT_EUR, CLOSE_DATE,
               DAYS_IN_STAGE, WON_LOST_REASON
        FROM CRM.OPPORTUNITIES
        WHERE ACCOUNT_ID = %s
        ORDER BY CLOSE_DATE DESC
        """,
        (account_id,),
    )


def get_recent_activities(account_id: str, limit: int = 15) -> list[dict]:
    return run_query(
        """
        SELECT ACTIVITY_DATE, ACTIVITY_TYPE, SUBJECT, SUMMARY, OWNER_AE
        FROM CRM.ACTIVITIES
        WHERE ACCOUNT_ID = %s
        ORDER BY ACTIVITY_DATE DESC
        LIMIT %s
        """,
        (account_id, limit),
    )


def get_product_usage(account_id: str, months: int = 6) -> list[dict]:
    return run_query(
        """
        SELECT MONTH, MONTHLY_ACTIVE_USERS, LOGINS, PAYROLL_RUNS,
               PERFORMANCE_MODULE_ACTIVE, PERFORMANCE_CYCLES_ACTIVE,
               RECRUITING_MODULE_ACTIVE
        FROM PRODUCT.USAGE
        WHERE ACCOUNT_ID = %s
        ORDER BY MONTH DESC
        LIMIT %s
        """,
        (account_id, months),
    )


def get_support_tickets(account_id: str) -> list[dict]:
    return run_query(
        """
        SELECT TICKET_ID, CREATED_DATE, RESOLVED_DATE, PRIORITY, STATUS,
               SUBJECT, SUMMARY
        FROM SUPPORT.TICKETS
        WHERE ACCOUNT_ID = %s
        ORDER BY CREATED_DATE DESC
        """,
        (account_id,),
    )
