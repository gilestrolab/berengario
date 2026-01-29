"""
Tests for thread-safe context management.

Tests contextvars-based context isolation across threads and async tasks.
"""

import concurrent.futures
import time

import pytest

from src.rag.tools.context import (
    clear_tool_context,
    get_tool_context,
    get_user_email,
    is_admin,
    is_email_request,
    set_tool_context,
    validate_admin_access,
)


class TestContextBasics:
    """Test basic context operations."""

    def test_set_and_get_context(self):
        """Test setting and getting context values."""
        set_tool_context(
            user_email="test@example.com", is_admin=True, is_email_request=False
        )

        context = get_tool_context()
        assert context["user_email"] == "test@example.com"
        assert context["is_admin"] is True
        assert context["is_email_request"] is False

    def test_clear_context(self):
        """Test clearing context resets to defaults."""
        set_tool_context(
            user_email="test@example.com", is_admin=True, is_email_request=True
        )

        clear_tool_context()

        context = get_tool_context()
        assert context["user_email"] == "unknown"
        assert context["is_admin"] is False
        assert context["is_email_request"] is False

    def test_helper_functions(self):
        """Test helper functions for context access."""
        set_tool_context(
            user_email="admin@example.com", is_admin=True, is_email_request=True
        )

        assert get_user_email() == "admin@example.com"
        assert is_admin() is True
        assert is_email_request() is True

    def test_default_values(self):
        """Test default values when context not set."""
        clear_tool_context()

        assert get_user_email() == "unknown"
        assert is_admin() is False
        assert is_email_request() is False


class TestAdminValidation:
    """Test admin access validation."""

    def test_validate_admin_success(self):
        """Test admin validation succeeds for admin users."""
        set_tool_context(
            user_email="admin@example.com", is_admin=True, is_email_request=False
        )

        # Should not raise
        validate_admin_access()

    def test_validate_admin_failure(self):
        """Test admin validation fails for non-admin users."""
        set_tool_context(
            user_email="user@example.com", is_admin=False, is_email_request=False
        )

        with pytest.raises(PermissionError) as exc_info:
            validate_admin_access()

        assert "admin" in str(exc_info.value).lower()
        assert "user@example.com" in str(exc_info.value)


class TestThreadSafety:
    """Test thread safety using concurrent execution."""

    def test_concurrent_context_isolation(self):
        """Test that contexts are isolated across threads."""

        def worker(user_id: int, delay: float) -> dict:
            """Worker function that sets context, sleeps, then reads it."""
            email = f"user{user_id}@example.com"
            is_adm = user_id % 2 == 0  # Even users are admins

            set_tool_context(user_email=email, is_admin=is_adm, is_email_request=False)

            # Sleep to allow other threads to set their context
            time.sleep(delay)

            # Read context back - should be unchanged
            context = get_tool_context()

            return {
                "user_id": user_id,
                "expected_email": email,
                "actual_email": context["user_email"],
                "expected_admin": is_adm,
                "actual_admin": context["is_admin"],
            }

        # Run 10 workers concurrently with varying delays
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [
                executor.submit(worker, i, delay=0.01 * (i % 3)) for i in range(10)
            ]

            results = [future.result() for future in futures]

        # Verify each thread maintained its own context
        for result in results:
            assert (
                result["expected_email"] == result["actual_email"]
            ), f"Context leaked for user {result['user_id']}"
            assert (
                result["expected_admin"] == result["actual_admin"]
            ), f"Admin status leaked for user {result['user_id']}"

    def test_concurrent_admin_validation(self):
        """Test admin validation works correctly across threads."""

        def admin_worker(user_id: int) -> dict:
            """Worker that validates admin access."""
            is_adm = user_id % 2 == 0
            set_tool_context(
                user_email=f"user{user_id}@example.com",
                is_admin=is_adm,
                is_email_request=False,
            )

            # Small delay to allow context switching
            time.sleep(0.001)

            try:
                validate_admin_access()
                return {"user_id": user_id, "success": True, "error": None}
            except PermissionError as e:
                return {"user_id": user_id, "success": False, "error": str(e)}

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(admin_worker, i) for i in range(10)]
            results = [future.result() for future in futures]

        # Verify validation worked correctly for each thread
        for result in results:
            user_id = result["user_id"]
            is_expected_admin = user_id % 2 == 0

            if is_expected_admin:
                assert result[
                    "success"
                ], f"Admin user {user_id} should have passed validation"
            else:
                assert not result[
                    "success"
                ], f"Non-admin user {user_id} should have failed validation"
                assert "admin" in result["error"].lower()

    def test_concurrent_mixed_operations(self):
        """Test mixed read/write operations across threads."""

        def mixed_worker(user_id: int) -> list:
            """Worker that performs multiple context operations."""
            operations = []

            # Set initial context
            email1 = f"user{user_id}_v1@example.com"
            set_tool_context(user_email=email1, is_admin=False, is_email_request=False)
            operations.append(("set", email1, get_user_email()))

            # Small delay
            time.sleep(0.001)

            # Read context
            operations.append(("read", email1, get_user_email()))

            # Update context
            email2 = f"user{user_id}_v2@example.com"
            set_tool_context(user_email=email2, is_admin=True, is_email_request=True)
            operations.append(("update", email2, get_user_email()))

            # Read again
            operations.append(("read2", email2, get_user_email()))

            return operations

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(mixed_worker, i) for i in range(5)]
            results = [future.result() for future in futures]

        # Verify all operations maintained correct context
        for user_id, operations in enumerate(results):
            for op_name, expected, actual in operations:
                assert (
                    expected == actual
                ), f"User {user_id} {op_name}: expected {expected}, got {actual}"


class TestEmailRequestFlag:
    """Test is_email_request flag behavior."""

    def test_email_request_true(self):
        """Test email request flag when set to true."""
        set_tool_context(
            user_email="test@example.com", is_admin=False, is_email_request=True
        )

        assert is_email_request() is True

    def test_email_request_false(self):
        """Test email request flag when set to false."""
        set_tool_context(
            user_email="test@example.com", is_admin=False, is_email_request=False
        )

        assert is_email_request() is False

    def test_email_request_default(self):
        """Test email request flag defaults to False."""
        set_tool_context(user_email="test@example.com", is_admin=False)

        assert is_email_request() is False


class TestContextIsolation:
    """Test context isolation between sequential operations."""

    def test_sequential_context_changes(self):
        """Test that sequential context changes don't interfere."""
        # First user
        set_tool_context(
            user_email="user1@example.com", is_admin=True, is_email_request=False
        )
        assert get_user_email() == "user1@example.com"
        assert is_admin() is True

        # Second user
        set_tool_context(
            user_email="user2@example.com", is_admin=False, is_email_request=True
        )
        assert get_user_email() == "user2@example.com"
        assert is_admin() is False
        assert is_email_request() is True

        # Third user
        set_tool_context(
            user_email="user3@example.com", is_admin=True, is_email_request=True
        )
        assert get_user_email() == "user3@example.com"
        assert is_admin() is True
        assert is_email_request() is True

    def test_partial_context_updates(self):
        """Test that all fields are updated even if some don't change."""
        # Set initial context
        set_tool_context(
            user_email="user1@example.com", is_admin=True, is_email_request=True
        )

        # Update with different values
        set_tool_context(
            user_email="user2@example.com", is_admin=False, is_email_request=False
        )

        # All fields should reflect new values
        context = get_tool_context()
        assert context["user_email"] == "user2@example.com"
        assert context["is_admin"] is False
        assert context["is_email_request"] is False
