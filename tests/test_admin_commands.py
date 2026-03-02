"""
Tests for admin email commands (add team members via email).
"""

from unittest.mock import MagicMock

from src.email.admin_commands import (
    AddUserCommand,
    detect_add_user_command,
    execute_add_user_mt,
    execute_add_user_st,
    parse_add_user_command,
)

# ---------------------------------------------------------------------------
# Detection tests
# ---------------------------------------------------------------------------


class TestDetectAddUserCommand:
    """Tests for detect_add_user_command()."""

    def test_simple_add(self):
        assert detect_add_user_command("", "add marcus@example.com to the team")

    def test_natural_language(self):
        assert detect_add_user_command(
            "", "Hi Berengario, please add Marcus <marcus@example.com> to the team"
        )

    def test_invite_synonym(self):
        assert detect_add_user_command("", "invite alice@example.com as a teacher")

    def test_enroll_synonym(self):
        assert detect_add_user_command("", "enroll bob@example.com")

    def test_register_synonym(self):
        assert detect_add_user_command("", "register carol@example.com as querier")

    def test_grant_access(self):
        assert detect_add_user_command("", "grant access to dave@example.com")

    def test_give_access(self):
        assert detect_add_user_command("", "give access to eve@example.com")

    def test_include_synonym(self):
        assert detect_add_user_command("", "include frank@test.org in the team")

    def test_subject_line_detection(self):
        assert detect_add_user_command("Add user@example.com", "")

    def test_angle_bracket_email(self):
        assert detect_add_user_command(
            "", "please add <marcus@example.com> as a teacher"
        )

    def test_email_first_pattern(self):
        assert detect_add_user_command("", "marcus@example.com as teacher")

    def test_email_first_to_team(self):
        assert detect_add_user_command("", "marcus@example.com to the team")

    def test_no_false_positive_normal_query(self):
        """Normal query mentioning an email should not trigger."""
        assert not detect_add_user_command(
            "Question", "What emails did marcus@example.com send last week?"
        )

    def test_no_false_positive_vacation_query(self):
        assert not detect_add_user_command(
            "Vacation policy", "What is the vacation policy?"
        )

    def test_no_false_positive_mention_email(self):
        assert not detect_add_user_command(
            "", "Please forward the report to marcus@example.com"
        )

    def test_empty_inputs(self):
        assert not detect_add_user_command("", "")


# ---------------------------------------------------------------------------
# Parsing tests
# ---------------------------------------------------------------------------


class TestParseAddUserCommand:
    """Tests for parse_add_user_command()."""

    def test_default_role_is_querier(self):
        cmd = parse_add_user_command("", "add marcus@example.com to the team")
        assert cmd is not None
        assert cmd.email == "marcus@example.com"
        assert cmd.role == "querier"
        assert cmd.error is None

    def test_teacher_role(self):
        cmd = parse_add_user_command("", "add marcus@example.com as a teacher")
        assert cmd is not None
        assert cmd.email == "marcus@example.com"
        assert cmd.role == "teacher"
        assert cmd.error is None

    def test_teacher_keyword_nearby(self):
        cmd = parse_add_user_command(
            "", "invite marcus@example.com — they'll be a teacher"
        )
        assert cmd is not None
        assert cmd.role == "teacher"

    def test_admin_role_rejected(self):
        cmd = parse_add_user_command("", "add marcus@example.com as admin")
        assert cmd is not None
        assert cmd.email == "marcus@example.com"
        assert cmd.error == "admin_role_requested"

    def test_angle_bracket_email(self):
        cmd = parse_add_user_command("", "add <Marcus@Example.COM> to the team")
        assert cmd is not None
        assert cmd.email == "marcus@example.com"  # lowercased

    def test_no_match_returns_none(self):
        cmd = parse_add_user_command("Hello", "What is the vacation policy?")
        assert cmd is None

    def test_email_first_as_teacher(self):
        cmd = parse_add_user_command("", "marcus@example.com as teacher")
        assert cmd is not None
        assert cmd.email == "marcus@example.com"
        assert cmd.role == "teacher"


# ---------------------------------------------------------------------------
# ST execution tests
# ---------------------------------------------------------------------------


class TestExecuteAddUserST:
    """Tests for execute_add_user_st()."""

    def test_add_querier(self):
        """Adding a querier adds to queriers whitelist only."""
        wm = MagicMock()
        wm.add_entry.return_value = True
        reload_cb = MagicMock()

        cmd = AddUserCommand(email="alice@example.com", role="querier")
        success, msg = execute_add_user_st(cmd, wm, reload_cb)

        assert success is True
        assert "alice@example.com" in msg
        assert "querier" in msg
        wm.add_entry.assert_called_once_with("queriers", "alice@example.com")
        reload_cb.assert_called_once()

    def test_add_teacher_also_adds_to_queriers(self):
        """Adding a teacher adds to both teachers and queriers."""
        wm = MagicMock()
        wm.add_entry.return_value = True
        reload_cb = MagicMock()

        cmd = AddUserCommand(email="bob@example.com", role="teacher")
        success, msg = execute_add_user_st(cmd, wm, reload_cb)

        assert success is True
        assert "teacher" in msg
        assert wm.add_entry.call_count == 2
        wm.add_entry.assert_any_call("queriers", "bob@example.com")
        wm.add_entry.assert_any_call("teachers", "bob@example.com")

    def test_already_exists(self):
        """If user already in whitelist, report no changes."""
        wm = MagicMock()
        wm.add_entry.return_value = False  # already exists
        reload_cb = MagicMock()

        cmd = AddUserCommand(email="existing@example.com", role="querier")
        success, msg = execute_add_user_st(cmd, wm, reload_cb)

        assert success is True
        assert "already a member" in msg

    def test_exception_handling(self):
        """Exceptions are caught and reported."""
        wm = MagicMock()
        wm.add_entry.side_effect = IOError("Permission denied")
        reload_cb = MagicMock()

        cmd = AddUserCommand(email="fail@example.com", role="querier")
        success, msg = execute_add_user_st(cmd, wm, reload_cb)

        assert success is False
        assert "couldn't add" in msg


# ---------------------------------------------------------------------------
# MT execution tests
# ---------------------------------------------------------------------------


class TestExecuteAddUserMT:
    """Tests for execute_add_user_mt()."""

    def test_creates_tenant_user(self):
        """Creates a TenantUser record in platform DB."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter_by.return_value.first.return_value = (
            None  # no existing user
        )
        mock_db_manager = MagicMock()
        mock_db_manager.get_platform_session.return_value.__enter__ = MagicMock(
            return_value=mock_session
        )
        mock_db_manager.get_platform_session.return_value.__exit__ = MagicMock(
            return_value=False
        )

        cmd = AddUserCommand(email="new@example.com", role="querier")
        success, msg = execute_add_user_mt(
            cmd, tenant_id="t1", tenant_slug="test", db_manager=mock_db_manager
        )

        assert success is True
        assert "new@example.com" in msg
        assert "querier" in msg
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

    def test_already_exists_mt(self):
        """Reports when user already exists in tenant."""
        mock_existing = MagicMock()
        mock_session = MagicMock()
        mock_session.query.return_value.filter_by.return_value.first.return_value = (
            mock_existing
        )
        mock_db_manager = MagicMock()
        mock_db_manager.get_platform_session.return_value.__enter__ = MagicMock(
            return_value=mock_session
        )
        mock_db_manager.get_platform_session.return_value.__exit__ = MagicMock(
            return_value=False
        )

        cmd = AddUserCommand(email="existing@example.com", role="querier")
        success, msg = execute_add_user_mt(
            cmd, tenant_id="t1", tenant_slug="test", db_manager=mock_db_manager
        )

        assert success is True
        assert "already a member" in msg
        mock_session.add.assert_not_called()

    def test_creates_teacher(self):
        """Teacher role creates user with TEACHER enum."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter_by.return_value.first.return_value = None
        mock_db_manager = MagicMock()
        mock_db_manager.get_platform_session.return_value.__enter__ = MagicMock(
            return_value=mock_session
        )
        mock_db_manager.get_platform_session.return_value.__exit__ = MagicMock(
            return_value=False
        )

        cmd = AddUserCommand(email="teach@example.com", role="teacher")
        success, msg = execute_add_user_mt(
            cmd, tenant_id="t1", tenant_slug="test", db_manager=mock_db_manager
        )

        assert success is True
        assert "teacher" in msg
        # Verify the TenantUser was created with correct role
        added_user = mock_session.add.call_args[0][0]
        from src.platform.models import TenantUserRole

        assert added_user.role == TenantUserRole.TEACHER

    def test_exception_handling_mt(self):
        """DB exceptions are caught and reported."""
        mock_db_manager = MagicMock()
        mock_db_manager.get_platform_session.side_effect = Exception("DB down")

        cmd = AddUserCommand(email="fail@example.com", role="querier")
        success, msg = execute_add_user_mt(
            cmd, tenant_id="t1", tenant_slug="test", db_manager=mock_db_manager
        )

        assert success is False
        assert "couldn't add" in msg
