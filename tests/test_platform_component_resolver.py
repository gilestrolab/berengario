"""
Tests for ComponentResolver.

Verifies ST mode returns default components, MT mode resolves via factory,
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


class TestComponentResolverST:
    """Single-tenant mode tests."""

    def test_st_returns_default_components(self):
        """ST mode always returns the default components."""
        default = _make_components("default")
        resolver = ComponentResolver(multi_tenant=False, default_components=default)

        session = MagicMock()
        result = resolver.resolve(session)
        assert result is default

    def test_st_ignores_session_tenant_slug(self):
        """ST mode ignores any tenant_slug on the session."""
        default = _make_components("default")
        resolver = ComponentResolver(multi_tenant=False, default_components=default)

        session = MagicMock()
        session.tenant_slug = "should-be-ignored"
        result = resolver.resolve(session)
        assert result is default

    def test_st_raises_if_no_default_components(self):
        """ST mode raises ValueError if no default_components set."""
        resolver = ComponentResolver(multi_tenant=False, default_components=None)

        with pytest.raises(ValueError, match="No default components"):
            resolver.resolve(MagicMock())


class TestComponentResolverMT:
    """Multi-tenant mode tests."""

    def test_mt_resolves_from_factory(self):
        """MT mode calls factory.get_components_for_slug()."""
        expected = _make_components("acme")
        factory = MagicMock()
        factory.get_components_for_slug.return_value = expected

        resolver = ComponentResolver(multi_tenant=True, component_factory=factory)

        session = MagicMock()
        session.tenant_slug = "acme"
        result = resolver.resolve(session)

        assert result is expected
        factory.get_components_for_slug.assert_called_once_with("acme")

    def test_mt_raises_if_no_tenant_selected(self):
        """MT mode raises ValueError if session has no tenant_slug."""
        factory = MagicMock()
        resolver = ComponentResolver(multi_tenant=True, component_factory=factory)

        session = MagicMock()
        session.tenant_slug = None
        with pytest.raises(ValueError, match="No tenant selected"):
            resolver.resolve(session)

    def test_mt_raises_if_no_factory(self):
        """MT mode raises ValueError if no factory configured."""
        resolver = ComponentResolver(multi_tenant=True, component_factory=None)

        session = MagicMock()
        session.tenant_slug = "acme"
        with pytest.raises(ValueError, match="No component factory"):
            resolver.resolve(session)

    def test_mt_propagates_factory_errors(self):
        """MT mode propagates errors from factory."""
        factory = MagicMock()
        factory.get_components_for_slug.side_effect = ValueError(
            "Tenant not found: bad"
        )

        resolver = ComponentResolver(multi_tenant=True, component_factory=factory)

        session = MagicMock()
        session.tenant_slug = "bad"
        with pytest.raises(ValueError, match="Tenant not found"):
            resolver.resolve(session)
