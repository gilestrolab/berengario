"""
Tests for team_tools (MT team management via LLM tools).
"""

from unittest.mock import MagicMock, patch

from src.rag.tools.context import (
    clear_tool_context,
    get_tenant_id,
    set_tool_context,
)

# --- Context ContextVar tests ---


class TestTenantIdContextVar:
    """Tests for the tenant_id ContextVar in tool context."""

    def teardown_method(self):
        clear_tool_context()

    def test_get_tenant_id_default_none(self):
        """get_tenant_id() returns None by default."""
        clear_tool_context()
        assert get_tenant_id() is None

    def test_set_and_get_tenant_id(self):
        """set_tool_context with tenant_id makes it available via get_tenant_id."""
        set_tool_context(user_email="a@b.com", is_admin=True, tenant_id="t-123")
        assert get_tenant_id() == "t-123"

    def test_clear_resets_tenant_id(self):
        """clear_tool_context resets tenant_id to None."""
        set_tool_context(user_email="a@b.com", is_admin=True, tenant_id="t-123")
        clear_tool_context()
        assert get_tenant_id() is None


# --- add_team_member tests ---


class TestAddTeamMember:
    """Tests for the add_team_member tool function."""

    def teardown_method(self):
        clear_tool_context()
        # Reset cached engine between tests
        import src.rag.tools.team_tools as tt

        tt._platform_engine = None

    def test_add_querier(self):
        """Add user with default querier role."""
        set_tool_context(user_email="admin@co.com", is_admin=True, tenant_id="t-1")

        mock_session = MagicMock()
        mock_session.query.return_value.filter_by.return_value.first.return_value = None

        with (
            patch(
                "src.rag.tools.team_tools._get_platform_session",
                return_value=mock_session,
            ),
            patch("src.email.email_sender.send_welcome_email", return_value=True),
            patch("src.email.email_sender.EmailSender"),
        ):
            from src.rag.tools.team_tools import add_team_member

            result = add_team_member(email="user@co.com")

        assert result["success"] is True
        assert "user@co.com" in result["message"]
        assert "querier" in result["message"]
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

    def test_add_teacher(self):
        """Add user with teacher role."""
        set_tool_context(user_email="admin@co.com", is_admin=True, tenant_id="t-1")

        mock_session = MagicMock()
        mock_session.query.return_value.filter_by.return_value.first.return_value = None

        with (
            patch(
                "src.rag.tools.team_tools._get_platform_session",
                return_value=mock_session,
            ),
            patch("src.email.email_sender.send_welcome_email", return_value=True),
            patch("src.email.email_sender.EmailSender"),
        ):
            from src.rag.tools.team_tools import add_team_member

            result = add_team_member(email="teacher@co.com", role="teacher")

        assert result["success"] is True
        assert "teacher" in result["message"]

    def test_rejects_admin_role(self):
        """Reject admin role assignment via tool."""
        set_tool_context(user_email="admin@co.com", is_admin=True, tenant_id="t-1")

        from src.rag.tools.team_tools import add_team_member

        result = add_team_member(email="user@co.com", role="admin")

        assert result["success"] is False
        assert "admin" in result["message"].lower()
        assert "security" in result["message"].lower()

    def test_rejects_invalid_role(self):
        """Reject unrecognized role."""
        set_tool_context(user_email="admin@co.com", is_admin=True, tenant_id="t-1")

        from src.rag.tools.team_tools import add_team_member

        result = add_team_member(email="user@co.com", role="superuser")

        assert result["success"] is False
        assert "Invalid role" in result["message"]

    def test_rejects_non_mt_mode(self):
        """Return error when tenant_id is None (ST mode)."""
        set_tool_context(user_email="admin@co.com", is_admin=True)  # no tenant_id

        from src.rag.tools.team_tools import add_team_member

        result = add_team_member(email="user@co.com")

        assert result["success"] is False
        assert "multi-tenant" in result["message"].lower()
        assert "whitelist" in result["message"].lower()

    def test_existing_user(self):
        """Return message when user already exists."""
        set_tool_context(user_email="admin@co.com", is_admin=True, tenant_id="t-1")

        mock_existing = MagicMock()
        mock_existing.role.value = "querier"

        mock_session = MagicMock()
        mock_session.query.return_value.filter_by.return_value.first.return_value = (
            mock_existing
        )

        with patch(
            "src.rag.tools.team_tools._get_platform_session",
            return_value=mock_session,
        ):
            from src.rag.tools.team_tools import add_team_member

            result = add_team_member(email="user@co.com")

        assert result["success"] is True
        assert "already" in result["message"].lower()
        mock_session.add.assert_not_called()

    def test_non_admin_rejected(self):
        """Non-admin user gets PermissionError."""
        set_tool_context(user_email="user@co.com", is_admin=False, tenant_id="t-1")

        from src.rag.tools.team_tools import add_team_member

        result = add_team_member(email="other@co.com")

        assert result["success"] is False
        assert "permission" in result["message"].lower()

    def test_sends_welcome_email(self):
        """Welcome email is sent on successful add."""
        set_tool_context(user_email="admin@co.com", is_admin=True, tenant_id="t-1")

        mock_session = MagicMock()
        mock_session.query.return_value.filter_by.return_value.first.return_value = None

        with (
            patch(
                "src.rag.tools.team_tools._get_platform_session",
                return_value=mock_session,
            ),
            patch(
                "src.email.email_sender.send_welcome_email", return_value=True
            ) as mock_welcome,
            patch("src.email.email_sender.EmailSender"),
        ):
            from src.rag.tools.team_tools import add_team_member

            result = add_team_member(email="new@co.com", role="teacher")

        assert result["success"] is True
        mock_welcome.assert_called_once()
        call_kwargs = mock_welcome.call_args
        assert call_kwargs.kwargs["to_email"] == "new@co.com"
        assert call_kwargs.kwargs["role"] == "teacher"

    def test_normalizes_email(self):
        """Email is stripped and lowered."""
        set_tool_context(user_email="admin@co.com", is_admin=True, tenant_id="t-1")

        mock_session = MagicMock()
        mock_session.query.return_value.filter_by.return_value.first.return_value = None

        with (
            patch(
                "src.rag.tools.team_tools._get_platform_session",
                return_value=mock_session,
            ),
            patch("src.email.email_sender.send_welcome_email", return_value=True),
            patch("src.email.email_sender.EmailSender"),
        ):
            from src.rag.tools.team_tools import add_team_member

            result = add_team_member(email="  User@CO.com  ")

        assert result["success"] is True
        # Verify the filter_by call used normalized email
        mock_session.query.return_value.filter_by.assert_called_with(
            email="user@co.com", tenant_id="t-1"
        )


# --- remove_team_member tests ---


class TestRemoveTeamMember:
    """Tests for the remove_team_member tool function."""

    def teardown_method(self):
        clear_tool_context()
        import src.rag.tools.team_tools as tt

        tt._platform_engine = None

    def test_remove_existing(self):
        """Remove an existing team member."""
        set_tool_context(user_email="admin@co.com", is_admin=True, tenant_id="t-1")

        mock_user = MagicMock()
        mock_session = MagicMock()
        mock_session.query.return_value.filter_by.return_value.first.return_value = (
            mock_user
        )

        with patch(
            "src.rag.tools.team_tools._get_platform_session",
            return_value=mock_session,
        ):
            from src.rag.tools.team_tools import remove_team_member

            result = remove_team_member(email="user@co.com")

        assert result["success"] is True
        assert "removed" in result["message"].lower()
        mock_session.delete.assert_called_once_with(mock_user)
        mock_session.commit.assert_called_once()

    def test_remove_not_found(self):
        """Return not-found message for missing user."""
        set_tool_context(user_email="admin@co.com", is_admin=True, tenant_id="t-1")

        mock_session = MagicMock()
        mock_session.query.return_value.filter_by.return_value.first.return_value = None

        with patch(
            "src.rag.tools.team_tools._get_platform_session",
            return_value=mock_session,
        ):
            from src.rag.tools.team_tools import remove_team_member

            result = remove_team_member(email="ghost@co.com")

        assert result["success"] is False
        assert "not a member" in result["message"].lower()
        mock_session.delete.assert_not_called()

    def test_rejects_non_mt_mode(self):
        """Return error when not in MT mode."""
        set_tool_context(user_email="admin@co.com", is_admin=True)  # no tenant_id

        from src.rag.tools.team_tools import remove_team_member

        result = remove_team_member(email="user@co.com")

        assert result["success"] is False
        assert "multi-tenant" in result["message"].lower()

    def test_non_admin_rejected(self):
        """Non-admin user gets PermissionError."""
        set_tool_context(user_email="user@co.com", is_admin=False, tenant_id="t-1")

        from src.rag.tools.team_tools import remove_team_member

        result = remove_team_member(email="other@co.com")

        assert result["success"] is False
        assert "permission" in result["message"].lower()
