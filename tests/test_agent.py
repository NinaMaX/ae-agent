"""
Tests that need no Snowflake or Anthropic credentials - data/enablement/ is
committed, so PlaybookSearchTests runs against it directly. End-to-end agent
behavior with live data is verified via scenarios.py (manual transcripts)
and eval_suite.py (automated pass/fail), not here.
"""

import unittest

import agent
import playbook_search


class PlaybookSearchTests(unittest.TestCase):
    def test_finds_workday_battlecard_for_competitive_query(self):
        results = playbook_search.search("Workday competitive positioning")
        self.assertTrue(any("workday" in r["source"].lower() for r in results))

    def test_returns_nothing_for_query_with_no_matches(self):
        self.assertEqual(playbook_search.search("zzqqxxnonexistentgibberish"), [])


class AgentToolSchemaTests(unittest.TestCase):
    def test_every_tool_has_a_dispatch_path(self):
        dispatchable = {"search_playbook"} | set(agent._SNOWFLAKE_TOOLS)
        declared = {t["name"] for t in agent.TOOLS}
        self.assertEqual(declared, dispatchable)

    def test_unknown_tool_name_does_not_raise(self):
        result = agent._run_tool("not_a_real_tool", {})
        self.assertIn("Unknown tool", result)


if __name__ == "__main__":
    unittest.main()
