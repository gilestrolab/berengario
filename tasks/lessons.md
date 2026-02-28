# Lessons Learned

## 2026-02-28: Phase 3 Web Multi-Tenancy

### Module-level router singleton causes test failures
- **Problem**: `router = APIRouter(...)` at module level means `create_team_router()` appends routes to the *same* router instance across test calls, causing duplicate route registrations and unexpected responses.
- **Fix**: Create `router = APIRouter(...)` *inside* the factory function so each call gets a fresh router.

### DI changes break test fixtures that patch module-level attributes
- **Problem**: Moving `from src.email.db_manager import db_manager` to lazy import inside `__init__` means `patch("src.email.conversation_manager.db_manager", ...)` fails because the module no longer has that attribute.
- **Fix**: Pass the test db_manager directly via DI (`ConversationManager(db_manager=test_db_manager)`) instead of patching.

### TenantContext frozen dataclass field ordering
- When adding new fields to a frozen dataclass, add them in a logical position but ensure ALL callers (tests, factories, `from_settings()`, `from_tenant()`) are updated. Use `Optional[T] = None` for backward compatibility.
