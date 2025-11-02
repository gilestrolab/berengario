"""
Unit tests for email whitelist validator.

Tests whitelist validation with domain wildcards and individual addresses.
"""

from pathlib import Path
from tempfile import NamedTemporaryFile

from src.email.whitelist_validator import WhitelistValidator


class TestWhitelistValidator:
    """Tests for WhitelistValidator class."""

    def test_init_disabled(self):
        """Test initializing with whitelist disabled."""
        validator = WhitelistValidator(enabled=False)

        assert validator.enabled is False
        assert len(validator.whitelist_entries) == 0
        assert len(validator.domain_entries) == 0

    def test_init_with_inline_emails(self):
        """Test initializing with inline email addresses."""
        validator = WhitelistValidator(whitelist="alice@example.com,bob@example.com")

        assert validator.enabled is True
        assert len(validator.whitelist_entries) == 2
        assert "alice@example.com" in validator.whitelist_entries
        assert "bob@example.com" in validator.whitelist_entries

    def test_init_with_inline_domains(self):
        """Test initializing with inline domain wildcards."""
        validator = WhitelistValidator(whitelist="@imperial.ac.uk,@ic.ac.uk")

        assert len(validator.domain_entries) == 2
        assert "@imperial.ac.uk" in validator.domain_entries
        assert "@ic.ac.uk" in validator.domain_entries

    def test_init_with_mixed_inline(self):
        """Test initializing with mixed emails and domains."""
        validator = WhitelistValidator(
            whitelist="alice@example.com,@imperial.ac.uk,bob@test.org"
        )

        assert len(validator.whitelist_entries) == 2
        assert len(validator.domain_entries) == 1
        assert "alice@example.com" in validator.whitelist_entries
        assert "@imperial.ac.uk" in validator.domain_entries

    def test_init_with_file(self):
        """Test initializing with file-based whitelist."""
        # Create temporary whitelist file
        with NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            f.write("# Comment line\n")
            f.write("\n")  # Empty line
            f.write("alice@example.com\n")
            f.write("@imperial.ac.uk\n")
            f.write("bob@test.org\n")
            temp_file = Path(f.name)

        try:
            validator = WhitelistValidator(whitelist_file=temp_file)

            assert len(validator.whitelist_entries) == 2
            assert len(validator.domain_entries) == 1
            assert "alice@example.com" in validator.whitelist_entries
            assert "@imperial.ac.uk" in validator.domain_entries
        finally:
            temp_file.unlink()

    def test_init_with_invalid_entries(self):
        """Test initializing with invalid entries (should skip them)."""
        validator = WhitelistValidator(
            whitelist="alice@example.com,invalid-entry,@imperial.ac.uk"
        )

        # Invalid entry should be skipped
        assert len(validator.whitelist_entries) == 1
        assert len(validator.domain_entries) == 1

    def test_is_allowed_disabled(self):
        """Test is_allowed when whitelist is disabled."""
        validator = WhitelistValidator(enabled=False)

        # All emails allowed when disabled
        assert validator.is_allowed("anyone@anywhere.com") is True
        assert validator.is_allowed("test@spam.com") is True

    def test_is_allowed_exact_match(self):
        """Test is_allowed with exact email match."""
        validator = WhitelistValidator(whitelist="alice@example.com")

        assert validator.is_allowed("alice@example.com") is True
        assert validator.is_allowed("ALICE@EXAMPLE.COM") is True  # Case insensitive
        assert validator.is_allowed("bob@example.com") is False

    def test_is_allowed_domain_match(self):
        """Test is_allowed with domain wildcard match."""
        validator = WhitelistValidator(whitelist="@imperial.ac.uk")

        assert validator.is_allowed("alice@imperial.ac.uk") is True
        assert validator.is_allowed("bob@imperial.ac.uk") is True
        assert validator.is_allowed("anyone@IMPERIAL.AC.UK") is True  # Case insensitive
        assert validator.is_allowed("test@other.com") is False

    def test_is_allowed_mixed_whitelist(self):
        """Test is_allowed with both emails and domains."""
        validator = WhitelistValidator(
            whitelist="alice@example.com,@imperial.ac.uk,bob@test.org"
        )

        # Exact matches
        assert validator.is_allowed("alice@example.com") is True
        assert validator.is_allowed("bob@test.org") is True

        # Domain matches
        assert validator.is_allowed("anyone@imperial.ac.uk") is True
        assert validator.is_allowed("staff@imperial.ac.uk") is True

        # No match
        assert validator.is_allowed("charlie@other.com") is False

    def test_is_allowed_empty_email(self):
        """Test is_allowed with empty email address."""
        validator = WhitelistValidator(whitelist="alice@example.com")

        assert validator.is_allowed("") is False
        assert validator.is_allowed(None) is False

    def test_is_allowed_empty_whitelist(self):
        """Test is_allowed with empty whitelist (enabled but empty)."""
        validator = WhitelistValidator(whitelist="", enabled=True)

        # No entries in whitelist - nothing should be allowed
        assert validator.is_allowed("alice@example.com") is False

    def test_is_allowed_whitespace_handling(self):
        """Test is_allowed handles whitespace correctly."""
        validator = WhitelistValidator(whitelist="alice@example.com")

        assert validator.is_allowed("  alice@example.com  ") is True

    def test_add_entry_email(self):
        """Test adding email address at runtime."""
        validator = WhitelistValidator(whitelist="alice@example.com")

        result = validator.add_entry("bob@example.com")

        assert result is True
        assert "bob@example.com" in validator.whitelist_entries
        assert validator.is_allowed("bob@example.com") is True

    def test_add_entry_domain(self):
        """Test adding domain at runtime."""
        validator = WhitelistValidator(whitelist="alice@example.com")

        result = validator.add_entry("@imperial.ac.uk")

        assert result is True
        assert "@imperial.ac.uk" in validator.domain_entries
        assert validator.is_allowed("anyone@imperial.ac.uk") is True

    def test_add_entry_duplicate(self):
        """Test adding duplicate entry."""
        validator = WhitelistValidator(whitelist="alice@example.com")

        result = validator.add_entry("alice@example.com")

        assert result is False  # Already exists

    def test_add_entry_invalid(self):
        """Test adding invalid entry."""
        validator = WhitelistValidator(whitelist="alice@example.com")

        result = validator.add_entry("invalid-entry")

        assert result is False

    def test_remove_entry_email(self):
        """Test removing email address."""
        validator = WhitelistValidator(whitelist="alice@example.com,bob@example.com")

        result = validator.remove_entry("alice@example.com")

        assert result is True
        assert "alice@example.com" not in validator.whitelist_entries
        assert validator.is_allowed("alice@example.com") is False

    def test_remove_entry_domain(self):
        """Test removing domain."""
        validator = WhitelistValidator(whitelist="@imperial.ac.uk,@ic.ac.uk")

        result = validator.remove_entry("@imperial.ac.uk")

        assert result is True
        assert "@imperial.ac.uk" not in validator.domain_entries
        assert validator.is_allowed("anyone@imperial.ac.uk") is False

    def test_remove_entry_not_found(self):
        """Test removing non-existent entry."""
        validator = WhitelistValidator(whitelist="alice@example.com")

        result = validator.remove_entry("bob@example.com")

        assert result is False

    def test_get_whitelist_summary(self):
        """Test getting whitelist summary."""
        validator = WhitelistValidator(
            whitelist="alice@example.com,bob@example.com,@imperial.ac.uk"
        )

        summary = validator.get_whitelist_summary()

        assert summary["enabled"] is True
        assert summary["email_count"] == 2
        assert summary["domain_count"] == 1
        assert "alice@example.com" in summary["emails"]
        assert "@imperial.ac.uk" in summary["domains"]

    def test_get_whitelist_summary_disabled(self):
        """Test getting summary when disabled."""
        validator = WhitelistValidator(enabled=False)

        summary = validator.get_whitelist_summary()

        assert summary["enabled"] is False
        assert summary["email_count"] == 0
        assert summary["domain_count"] == 0

    def test_case_insensitive_domains(self):
        """Test domain matching is case insensitive."""
        validator = WhitelistValidator(whitelist="@IMPERIAL.AC.UK")

        assert validator.is_allowed("alice@imperial.ac.uk") is True
        assert validator.is_allowed("bob@Imperial.Ac.Uk") is True
        assert validator.is_allowed("test@IMPERIAL.AC.UK") is True

    def test_file_not_found(self):
        """Test handling of non-existent file."""
        validator = WhitelistValidator(whitelist_file=Path("/nonexistent/file.txt"))

        # Should not raise error, just log warning
        assert len(validator.whitelist_entries) == 0
        assert len(validator.domain_entries) == 0

    def test_combined_file_and_inline(self):
        """Test combining file-based and inline whitelist."""
        # Create temporary file
        with NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            f.write("alice@example.com\n")
            f.write("@imperial.ac.uk\n")
            temp_file = Path(f.name)

        try:
            validator = WhitelistValidator(
                whitelist="bob@example.com,@ic.ac.uk", whitelist_file=temp_file
            )

            # Should have entries from both sources
            assert len(validator.whitelist_entries) == 2  # alice, bob
            assert len(validator.domain_entries) == 2  # @imperial, @ic
            assert "alice@example.com" in validator.whitelist_entries
            assert "bob@example.com" in validator.whitelist_entries
            assert "@imperial.ac.uk" in validator.domain_entries
            assert "@ic.ac.uk" in validator.domain_entries
        finally:
            temp_file.unlink()
