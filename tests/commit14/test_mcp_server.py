from __future__ import annotations

import itertools
import unittest
from typing import Any

from starlette.testclient import TestClient

from src.mcp_server import MCPServerConfig, SERVER_NAME, SERVER_VERSION, create_server


TOKEN = "commit14-integration-token-32-chars"
BASE_URL = "http://127.0.0.1:8000"
MCP_HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
}


class MCPServerIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = create_server(MCPServerConfig(bearer_token=TOKEN))
        cls.client_context = TestClient(
            cls.server.streamable_http_app(),
            base_url=BASE_URL,
        )
        cls.client = cls.client_context.__enter__()
        cls.request_ids = itertools.count(1)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client_context.__exit__(None, None, None)
        cls.server.close()

    def post(
        self,
        method: str,
        params: dict[str, Any],
        *,
        token: str | None = TOKEN,
    ):
        headers = dict(MCP_HEADERS)
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        return self.client.post(
            "/mcp",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": next(self.request_ids),
                "method": method,
                "params": params,
            },
        )

    def list_tools(self) -> list[dict[str, Any]]:
        response = self.post("tools/list", {})
        self.assertEqual(response.status_code, 200)
        return response.json()["result"]["tools"]

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        response = self.post(
            "tools/call",
            {"name": name, "arguments": arguments},
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["result"]

    def test_01_initialize_identifies_server_and_protocol(self):
        response = self.post("initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "commit14-tests", "version": "1"},
        })

        self.assertEqual(response.status_code, 200)
        result = response.json()["result"]
        self.assertEqual(result["serverInfo"]["name"], SERVER_NAME)
        self.assertEqual(result["serverInfo"]["version"], "1.29.0")
        self.assertIn("tools", result["capabilities"])

    def test_02_missing_token_is_rejected(self):
        response = self.post("tools/list", {}, token=None)

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"], "invalid_token")
        self.assertIn("resource_metadata", response.headers["www-authenticate"])

    def test_03_wrong_token_is_rejected(self):
        response = self.post("tools/list", {}, token="wrong-token-value")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"], "invalid_token")

    def test_04_resource_metadata_is_public_and_scoped(self):
        response = self.client.get("/.well-known/oauth-protected-resource/mcp")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["resource"], f"{BASE_URL}/mcp")
        self.assertEqual(payload["scopes_supported"], ["signaldesk:read"])
        self.assertEqual(payload["bearer_methods_supported"], ["header"])

    def test_05_exactly_four_roadmap_tools_are_exposed(self):
        names = {tool["name"] for tool in self.list_tools()}

        self.assertEqual(names, {
            "campaign_eligibility",
            "customer_events",
            "customer_profile",
            "knowledge_search",
        })

    def test_06_every_tool_has_a_specific_description(self):
        tools = self.list_tools()

        self.assertTrue(all(len(tool["description"]) >= 40 for tool in tools))

    def test_07_every_input_schema_rejects_extra_properties(self):
        tools = self.list_tools()

        self.assertTrue(all(
            tool["inputSchema"]["additionalProperties"] is False
            for tool in tools
        ))

    def test_08_every_tool_publishes_structured_output_schema(self):
        tools = self.list_tools()

        self.assertTrue(all("outputSchema" in tool for tool in tools))
        self.assertTrue(all(
            "success" in tool["outputSchema"]["properties"]
            for tool in tools
        ))

    def test_09_every_tool_declares_read_only_closed_world_behavior(self):
        tools = self.list_tools()

        for tool in tools:
            annotations = tool["annotations"]
            self.assertTrue(annotations["readOnlyHint"])
            self.assertTrue(annotations["idempotentHint"])
            self.assertFalse(annotations["destructiveHint"])
            self.assertFalse(annotations["openWorldHint"])
            self.assertEqual(tool["_meta"]["signaldesk/sideEffects"], "none")
            self.assertEqual(
                tool["_meta"]["signaldesk/serverVersion"],
                SERVER_VERSION,
            )

    def test_10_customer_profile_is_pii_safe(self):
        result = self.call_tool(
            "customer_profile",
            {"customer_id": "C0000001"},
        )

        self.assertFalse(result["isError"])
        output = result["structuredContent"]
        self.assertTrue(output["success"])
        self.assertEqual(output["tool_name"], "customer_profile")
        self.assertFalse(output["output"]["pii_included"])
        self.assertNotIn("email", output["output"])
        self.assertNotIn("phone", output["output"])

    def test_11_unknown_customer_returns_structured_not_found(self):
        result = self.call_tool(
            "customer_profile",
            {"customer_id": "C9999999"},
        )

        self.assertFalse(result["isError"])
        output = result["structuredContent"]
        self.assertFalse(output["success"])
        self.assertEqual(output["error"]["code"], "NOT_FOUND")

    def test_12_invalid_customer_id_fails_schema_validation(self):
        result = self.call_tool(
            "customer_profile",
            {"customer_id": "not-a-customer"},
        )

        self.assertTrue(result["isError"])
        self.assertIn("string_pattern_mismatch", result["content"][0]["text"])

    def test_13_undeclared_profile_argument_fails_schema_validation(self):
        result = self.call_tool(
            "customer_profile",
            {"customer_id": "C0000001", "include_email": True},
        )

        self.assertTrue(result["isError"])
        self.assertIn("extra_forbidden", result["content"][0]["text"])

    def test_14_customer_events_are_bounded_and_filtered(self):
        result = self.call_tool("customer_events", {
            "customer_id": "C0000001",
            "days": 90,
            "limit": 3,
            "event_types": ["product_view"],
        })

        output = result["structuredContent"]["output"]
        self.assertLessEqual(output["returned_count"], 3)
        self.assertEqual(output["event_types"], ["product_view"])
        self.assertTrue(all(
            event["event_type"] == "product_view" for event in output["events"]
        ))

    def test_15_event_window_above_ninety_days_is_rejected(self):
        result = self.call_tool("customer_events", {
            "customer_id": "C0000001",
            "days": 91,
        })

        self.assertTrue(result["isError"])
        self.assertIn("less_than_equal", result["content"][0]["text"])

    def test_16_unknown_event_type_is_rejected(self):
        result = self.call_tool("customer_events", {
            "customer_id": "C0000001",
            "event_types": ["password_changed"],
        })

        self.assertTrue(result["isError"])
        self.assertIn("literal_error", result["content"][0]["text"])

    def test_17_knowledge_search_returns_only_approved_current_documents(self):
        result = self.call_tool("knowledge_search", {
            "query": "email opt out suppression",
            "top_k": 3,
            "families": ["consent"],
        })

        output = result["structuredContent"]["output"]
        self.assertEqual(output["returned_count"], 3)
        self.assertTrue(all(item["status"] == "CURRENT" for item in output["results"]))
        self.assertTrue(all(
            item["authority"] == "APPROVED" for item in output["results"]
        ))
        self.assertTrue(all(item["family"] == "consent" for item in output["results"]))

    def test_18_knowledge_search_without_family_uses_bounded_default(self):
        result = self.call_tool(
            "knowledge_search",
            {"query": "shipping delay customer support"},
        )

        output = result["structuredContent"]["output"]
        self.assertLessEqual(output["returned_count"], 5)
        self.assertEqual(output["retrieval_method"], "lexical_current_approved")

    def test_19_unknown_knowledge_family_is_rejected(self):
        result = self.call_tool("knowledge_search", {
            "query": "customer policy",
            "families": ["internal_secrets"],
        })

        self.assertTrue(result["isError"])
        self.assertIn("literal_error", result["content"][0]["text"])

    def test_20_knowledge_top_k_above_ten_is_rejected(self):
        result = self.call_tool("knowledge_search", {
            "query": "customer policy",
            "top_k": 11,
        })

        self.assertTrue(result["isError"])
        self.assertIn("less_than_equal", result["content"][0]["text"])

    def test_21_campaign_eligibility_never_claims_final_eligibility(self):
        result = self.call_tool(
            "campaign_eligibility",
            {"customer_id": "C0000001"},
        )

        output = result["structuredContent"]["output"]
        self.assertIn(output["status"], {"BLOCKED", "REVIEW_REQUIRED"})
        self.assertTrue(all(
            channel["status"] in {"BLOCKED", "REVIEW_REQUIRED"}
            for channel in output["channel_results"]
        ))
        self.assertTrue(output["limitations"])
        self.assertIn("require review", " ".join(output["limitations"]))

    def test_22_campaign_channel_filter_returns_one_channel(self):
        result = self.call_tool("campaign_eligibility", {
            "customer_id": "C0000001",
            "channel": "EMAIL",
        })

        channels = result["structuredContent"]["output"]["channel_results"]
        self.assertEqual(len(channels), 1)
        self.assertEqual(channels[0]["channel"], "EMAIL")

    def test_23_unknown_campaign_channel_is_rejected(self):
        result = self.call_tool("campaign_eligibility", {
            "customer_id": "C0000001",
            "channel": "WHATSAPP",
        })

        self.assertTrue(result["isError"])
        self.assertIn("literal_error", result["content"][0]["text"])

    def test_24_unknown_mcp_tool_is_rejected(self):
        result = self.call_tool("execute_campaign", {"customer_id": "C0000001"})

        self.assertTrue(result["isError"])
        self.assertIn("Unknown tool", result["content"][0]["text"])

    def test_25_repeated_read_returns_same_business_output(self):
        first = self.call_tool("customer_profile", {"customer_id": "C0000001"})
        second = self.call_tool("customer_profile", {"customer_id": "C0000001"})

        first_output = first["structuredContent"]
        second_output = second["structuredContent"]
        first_output.pop("latency_ms")
        second_output.pop("latency_ms")
        self.assertEqual(first_output, second_output)

    def test_26_no_exposed_tool_name_implies_mutation(self):
        names = {tool["name"] for tool in self.list_tools()}

        mutation_terms = {"create", "delete", "execute", "issue", "send", "update"}
        self.assertTrue(all(
            not mutation_terms.intersection(name.split("_")) for name in names
        ))

    def test_27_server_config_repr_does_not_expose_token(self):
        config = MCPServerConfig(bearer_token=TOKEN)

        self.assertNotIn(TOKEN, repr(config))


if __name__ == "__main__":
    unittest.main()
