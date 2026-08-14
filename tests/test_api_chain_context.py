from framework.api_chain_context import ChainContext, extract_path
from runtime_environments import _parse_local_env_lines


def test_chain_context_preserves_types_and_renders_nested_templates():
    context = ChainContext()
    context.set("empty_leg_id", "956181556379160576")
    context.set("route_count", 2)

    rendered = context.render(
        {
            "id": "{{empty_leg_id}}",
            "count": "{{route_count}}",
            "url": "/empty-leg?emptyLegId={{empty_leg_id}}",
            "items": ["{{route_count}}"],
        }
    )

    assert rendered == {
        "id": "956181556379160576",
        "count": 2,
        "url": "/empty-leg?emptyLegId=956181556379160576",
        "items": [2],
    }


def test_chain_context_redacts_sensitive_values_and_email():
    context = ChainContext({"email_token"})
    context.set("subscription_email", "tester@example.com")
    context.set("email_empty_leg_id", "956181556379160576")
    context.set("email_token", "secret-token")
    context.record_step(
        "request",
        "passed",
        request={"email": "tester@example.com", "authorization": "Bearer secret"},
    )

    snapshot = context.public_snapshot()

    assert snapshot["subscription_email"] == "te***@example.com"
    assert snapshot["email_empty_leg_id"] == "956181556379160576"
    assert snapshot["email_token"] == "<redacted>"
    assert context.events[-1]["details"]["request"]["email"] == "te***@example.com"
    assert context.events[-1]["details"]["request"]["authorization"] == "<redacted>"


def test_extract_path_supports_dictionary_and_list_segments():
    payload = {"data": {"items": [{"id": "EL-001"}]}}

    assert extract_path(payload, "data.items.0.id") == "EL-001"


def test_local_env_duplicate_keys_use_last_definition():
    parsed = _parse_local_env_lines(
        [
            "JETBAY_TEST_DB_PASSWORD=old-value",
            "JETBAY_TEST_DB_PASSWORD=new-value",
        ]
    )

    assert parsed["JETBAY_TEST_DB_PASSWORD"] == "new-value"
