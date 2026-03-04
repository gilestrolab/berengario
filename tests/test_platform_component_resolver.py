"""
Tests for ComponentResolver.

Verifies resolve returns factory components for session tenant,
and error cases are handled properly.
"""

from unittest.mock import MagicMock

import pytest

from src.platform.component_factory import TenantComponents
from src.platform.component_resolver import ComponentResolver


def _make_components(slug="test"):
    """Create a mock TenantComponents with a given slug."""
    ctx = MagicMock()
    ctx.tenant_slug = slug
    return TenantComponents(
        context=ctx,
        kb_manager=MagicMock(),
        doc_processor=MagicMock(),
        rag_engine=MagicMock(),
        query_handler=MagicMock(),
        conversation_manager=MagicMock(),
    )


class TestComponentResolver:
    """Tests for ComponentResolver."""

    def test_resolves_from_factory(self):
        """Calls factory.get_components_for_slug() with session's tenant."""
        expected = _make_components("acme")
        factory = MagicMock()
        factory.get_components_for_slug.return_value = expected

        resolver = ComponentResolver(component_factory=factory)

        session = MagicMock()
        session.tenant_slug = "acme"
        result = resolver.resolve(session)

        assert result is expected
        factory.get_components_for_slug.assert_called_once_with("acme")

    def test_raises_if_no_tenant_selected(self):
        """Raises ValueError if session has no tenant_slug."""
        factory = MagicMock()
        resolver = ComponentResolver(component_factory=factory)

        session = MagicMock()
        session.tenant_slug = None
        with pytest.raises(ValueError, match="No tenant selected"):
            resolver.resolve(session)

    def test_raises_if_no_factory(self):
        """Raises ValueError if no factory configured."""
        resolver = ComponentResolver(component_factory=None)

        session = MagicMock()
        session.tenant_slug = "acme"
        with pytest.raises(ValueError, match="No component factory"):
            resolver.resolve(session)

    def test_propagates_factory_errors(self):
        """Propagates errors from factory."""
        factory = MagicMock()
        factory.get_components_for_slug.side_effect = ValueError(
            "Tenant not found: bad"
        )

        resolver = ComponentResolver(component_factory=factory)

        session = MagicMock()
        session.tenant_slug = "bad"
        with pytest.raises(ValueError, match="Tenant not found"):
            resolver.resolve(session)

    def test_accepts_extra_kwargs(self):
        """Accepts and ignores extra kwargs for backward compatibility."""
        factory = MagicMock()
        # Should not raise
        resolver = ComponentResolver(
            component_factory=factory,
            multi_tenant=True,
            default_components=None,
        )
        assert resolver._factory is factory
