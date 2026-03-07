"""Tests for security modules: PolicyEngine, URL validator, approval store."""

import asyncio
from unittest.mock import patch

import pytest

from agent_chat.security.approval_store import (
    ApprovalStatus,
    ApprovalStore,
    PendingApproval,
)
from agent_chat.security.policy import Decision, PolicyEngine, PolicyResult, _redact_args
from agent_chat.security.url_validator import (
    URLValidationError,
    is_allowed_content_type,
    validate_url,
)
from agent_chat.tools.base import Tool


# ========== Dummy tools for testing ==========

class ReadTool(Tool):
    name = "dummy_read"
    description = "A read-only tool"
    parameters = {"type": "object", "properties": {}}
    risk_level = "read"

    async def execute(self, arguments, context=None):
        return {"ok": True}


class WriteTool(Tool):
    name = "dummy_write"
    description = "A write tool"
    parameters = {"type": "object", "properties": {}}
    risk_level = "write"

    async def execute(self, arguments, context=None):
        return {"ok": True}


class DestructiveTool(Tool):
    name = "dummy_destructive"
    description = "A destructive tool"
    parameters = {"type": "object", "properties": {}}
    risk_level = "destructive"

    async def execute(self, arguments, context=None):
        return {"ok": True}


class AdminTool(Tool):
    name = "dummy_admin"
    description = "An admin tool"
    parameters = {"type": "object", "properties": {}}
    risk_level = "admin"
    required_scopes = {"admin:manage"}

    async def execute(self, arguments, context=None):
        return {"ok": True}


class ConfirmTool(Tool):
    name = "dummy_confirm"
    description = "Tool requiring confirmation"
    parameters = {"type": "object", "properties": {}}
    risk_level = "read"
    requires_confirmation = True

    async def execute(self, arguments, context=None):
        return {"ok": True}


class RedactTool(Tool):
    name = "dummy_redact"
    description = "Tool with redacted args"
    parameters = {"type": "object", "properties": {}}
    risk_level = "read"
    arg_redaction = ["password", "secret"]

    async def execute(self, arguments, context=None):
        return {"ok": True}


# ========== PolicyEngine Tests ==========

class TestPolicyEngine:
    def setup_method(self):
        self.engine = PolicyEngine()

    def test_read_tool_allowed(self):
        result = self.engine.evaluate(ReadTool(), {"query": "test"})
        assert result.decision == Decision.ALLOW

    def test_write_tool_confirm(self):
        result = self.engine.evaluate(WriteTool(), {"content": "x"})
        assert result.decision == Decision.CONFIRM

    def test_destructive_tool_confirm(self):
        result = self.engine.evaluate(DestructiveTool(), {})
        assert result.decision == Decision.CONFIRM

    def test_admin_tool_denied_without_scopes(self):
        result = self.engine.evaluate(AdminTool(), {})
        assert result.decision == Decision.DENY
        assert "admin:manage" in result.reason

    def test_admin_tool_allowed_with_scopes(self):
        result = self.engine.evaluate(AdminTool(), {}, user_scopes={"admin:manage"})
        # Admin tool with correct scopes still gets DENY (risk_level=admin)
        assert result.decision == Decision.DENY

    def test_requires_confirmation_overrides_read(self):
        result = self.engine.evaluate(ConfirmTool(), {})
        assert result.decision == Decision.CONFIRM

    def test_arg_redaction(self):
        args = {"username": "alice", "password": "secret123", "secret": "key"}
        result = self.engine.evaluate(RedactTool(), args)
        assert result.redacted_args["password"] == "***REDACTED***"
        assert result.redacted_args["secret"] == "***REDACTED***"
        assert result.redacted_args["username"] == "alice"

    def test_redact_args_helper(self):
        args = {"a": 1, "b": 2, "c": 3}
        redacted = _redact_args(args, ["b"])
        assert redacted["b"] == "***REDACTED***"
        assert redacted["a"] == 1
        assert args["b"] == 2  # original not modified


# ========== URL Validator Tests ==========

class TestURLValidator:
    def test_valid_public_url(self):
        # Mock DNS resolution to return a public IP
        with patch("agent_chat.security.url_validator.socket.getaddrinfo") as mock_dns:
            mock_dns.return_value = [
                (2, 1, 6, "", ("93.184.216.34", 0)),
            ]
            result = validate_url("https://example.com/page")
            assert result == "https://example.com/page"

    def test_blocked_scheme_ftp(self):
        with pytest.raises(URLValidationError, match="Blocked scheme"):
            validate_url("ftp://example.com/file")

    def test_blocked_scheme_file(self):
        with pytest.raises(URLValidationError, match="Blocked scheme"):
            validate_url("file:///etc/passwd")

    def test_blocked_localhost(self):
        with pytest.raises(URLValidationError, match="Blocked hostname"):
            validate_url("http://localhost/admin")

    def test_blocked_private_ip_10(self):
        with patch("agent_chat.security.url_validator.socket.getaddrinfo") as mock_dns:
            mock_dns.return_value = [(2, 1, 6, "", ("10.0.0.1", 0))]
            with pytest.raises(URLValidationError, match="private/reserved"):
                validate_url("http://internal.company.com")

    def test_blocked_private_ip_192_168(self):
        with patch("agent_chat.security.url_validator.socket.getaddrinfo") as mock_dns:
            mock_dns.return_value = [(2, 1, 6, "", ("192.168.1.1", 0))]
            with pytest.raises(URLValidationError, match="private/reserved"):
                validate_url("http://router.local")

    def test_blocked_private_ip_172(self):
        with patch("agent_chat.security.url_validator.socket.getaddrinfo") as mock_dns:
            mock_dns.return_value = [(2, 1, 6, "", ("172.16.0.1", 0))]
            with pytest.raises(URLValidationError, match="private/reserved"):
                validate_url("http://internal.corp")

    def test_blocked_loopback_127(self):
        with patch("agent_chat.security.url_validator.socket.getaddrinfo") as mock_dns:
            mock_dns.return_value = [(2, 1, 6, "", ("127.0.0.1", 0))]
            with pytest.raises(URLValidationError, match="private/reserved"):
                validate_url("http://evil.com")

    def test_allowed_benchmarking_range(self):
        """198.18.0.0/15 should NOT be blocked — VPN/proxy often uses this range."""
        with patch("agent_chat.security.url_validator.socket.getaddrinfo") as mock_dns:
            mock_dns.return_value = [(2, 1, 6, "", ("198.18.1.230", 0))]
            result = validate_url("https://docs.python.org")
            assert result == "https://docs.python.org"

    def test_blocked_metadata_endpoint(self):
        with patch("agent_chat.security.url_validator.socket.getaddrinfo") as mock_dns:
            mock_dns.return_value = [(2, 1, 6, "", ("169.254.169.254", 0))]
            with pytest.raises(URLValidationError, match="private/reserved"):
                validate_url("http://evil.com")

    def test_blocked_metadata_hostname(self):
        with pytest.raises(URLValidationError, match="Blocked hostname"):
            validate_url("http://metadata.google.internal/computeMetadata")

    def test_no_hostname(self):
        with pytest.raises(URLValidationError, match="no hostname"):
            validate_url("http://")

    def test_allowlist_pass(self):
        with patch("agent_chat.security.url_validator.socket.getaddrinfo") as mock_dns:
            mock_dns.return_value = [(2, 1, 6, "", ("93.184.216.34", 0))]
            result = validate_url("https://docs.example.com/page", allowlist=["example.com"])
            assert result

    def test_allowlist_block(self):
        with pytest.raises(URLValidationError, match="not in allow list"):
            validate_url("https://evil.com/page", allowlist=["example.com"])

    def test_denylist_block(self):
        with pytest.raises(URLValidationError, match="deny list"):
            validate_url("https://blocked.example.com", denylist=["blocked.example.com"])

    def test_denylist_subdomain(self):
        with pytest.raises(URLValidationError, match="deny list"):
            validate_url("https://sub.blocked.com", denylist=["blocked.com"])

    def test_content_type_allowed(self):
        assert is_allowed_content_type("text/html; charset=utf-8")
        assert is_allowed_content_type("application/json")
        assert is_allowed_content_type("text/plain")
        assert is_allowed_content_type(None)  # missing = allowed

    def test_content_type_blocked(self):
        assert not is_allowed_content_type("application/octet-stream")
        assert not is_allowed_content_type("image/png")
        assert not is_allowed_content_type("application/pdf")


# ========== Approval Store Tests ==========

class TestApprovalStore:
    def setup_method(self):
        self.store = ApprovalStore()

    def test_create_and_list(self):
        approval = self.store.create(
            run_id="run1",
            tool_name="web_fetch",
            arguments={"url": "https://example.com"},
            risk_level="write",
            reason="Write operation",
        )
        assert approval.status == ApprovalStatus.PENDING
        items = self.store.list_pending(run_id="run1")
        assert len(items) == 1
        assert items[0]["tool_name"] == "web_fetch"

    def test_resolve_approve(self):
        approval = self.store.create(
            run_id="run1", tool_name="test", arguments={},
            risk_level="write", reason="test",
        )
        result = self.store.resolve(approval.id, approved=True)
        assert result is not None
        assert result.status == ApprovalStatus.APPROVED
        # No longer in pending list
        assert len(self.store.list_pending()) == 0

    def test_resolve_deny(self):
        approval = self.store.create(
            run_id="run1", tool_name="test", arguments={},
            risk_level="write", reason="test",
        )
        result = self.store.resolve(approval.id, approved=False)
        assert result.status == ApprovalStatus.DENIED

    def test_resolve_nonexistent(self):
        result = self.store.resolve("nonexistent", approved=True)
        assert result is None

    def test_resolve_already_resolved(self):
        approval = self.store.create(
            run_id="run1", tool_name="test", arguments={},
            risk_level="write", reason="test",
        )
        self.store.resolve(approval.id, approved=True)
        # Second resolve should fail
        result = self.store.resolve(approval.id, approved=False)
        assert result is None

    def test_cleanup(self):
        self.store.create(
            run_id="run1", tool_name="a", arguments={},
            risk_level="write", reason="",
        )
        self.store.create(
            run_id="run2", tool_name="b", arguments={},
            risk_level="write", reason="",
        )
        self.store.cleanup("run1")
        # Only run2 should remain
        assert len(self.store.list_pending()) == 1

    @pytest.mark.asyncio
    async def test_approval_wait_approved(self):
        approval = self.store.create(
            run_id="run1", tool_name="test", arguments={},
            risk_level="write", reason="test",
        )

        async def approve_later():
            await asyncio.sleep(0.05)
            self.store.resolve(approval.id, approved=True)

        asyncio.create_task(approve_later())
        status = await approval.wait(timeout=2.0)
        assert status == ApprovalStatus.APPROVED

    @pytest.mark.asyncio
    async def test_approval_wait_timeout(self):
        approval = self.store.create(
            run_id="run1", tool_name="test", arguments={},
            risk_level="write", reason="test",
        )
        status = await approval.wait(timeout=0.05)
        assert status == ApprovalStatus.EXPIRED

    def test_filter_by_run_id(self):
        self.store.create(
            run_id="run1", tool_name="a", arguments={},
            risk_level="write", reason="",
        )
        self.store.create(
            run_id="run2", tool_name="b", arguments={},
            risk_level="write", reason="",
        )
        assert len(self.store.list_pending(run_id="run1")) == 1
        assert len(self.store.list_pending(run_id="run2")) == 1
        assert len(self.store.list_pending()) == 2

    def test_to_dict(self):
        approval = self.store.create(
            run_id="run1", tool_name="web_fetch",
            arguments={"url": "https://example.com"},
            risk_level="write", reason="Write op",
        )
        d = approval.to_dict()
        assert d["run_id"] == "run1"
        assert d["tool_name"] == "web_fetch"
        assert d["status"] == "pending"
        assert "created_at" in d


# ========== Tool Base Class Tests ==========

class TestToolBaseClass:
    def test_default_security_fields(self):
        tool = ReadTool()
        assert tool.requires_confirmation is False
        assert tool.required_scopes == set()
        assert tool.arg_redaction == []

    def test_custom_security_fields(self):
        tool = ConfirmTool()
        assert tool.requires_confirmation is True

    def test_admin_scopes(self):
        tool = AdminTool()
        assert tool.required_scopes == {"admin:manage"}

    def test_redaction_fields(self):
        tool = RedactTool()
        assert tool.arg_redaction == ["password", "secret"]

    def test_destructive_risk_level(self):
        tool = DestructiveTool()
        assert tool.risk_level == "destructive"
