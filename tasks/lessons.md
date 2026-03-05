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

## 2026-02-28: Phase 4 Email Multi-Tenancy

### "Thin wrapper + parameterized _with()" pattern for ST/MT dual mode
- **Pattern**: Extract the core logic into `_process_query_with(email, query_handler, conv_manager, ...)` accepting explicit dependencies, then make the original `_process_query()` a thin wrapper passing `self.*` and `settings.*`.
- **Benefit**: Zero behavior change for ST mode; MT mode calls `_with()` directly with tenant-specific components.
- **Applies to**: Any method that uses singletons/globals and needs per-tenant injection.

### Global dedup before MT fan-out
- **Pattern**: `MessageTracker.is_processed()` check stays at the top of `process_message()`, before any MT dispatch. This prevents the same email being processed N times across N tenants.
- **Key**: Mark processed globally once after fan-out completes (not per-tenant).

### f-strings without placeholders caught by Ruff F541
- **Problem**: Writing `error=f"static string"` triggers Ruff F541.
- **Fix**: Remove the `f` prefix when the string has no `{variable}` placeholders.

### Import ordering in lazy imports (Ruff I001)
- **Problem**: Lazy imports inside methods still need to follow isort ordering (alphabetical by module path).
- **Fix**: `from src.email.*` before `from src.platform.*` (e → p alphabetically).

## 2026-03-01: Phase 5 Platform Admin

### Avoid importing src.config in tests when data/ dirs may not be writable
- **Problem**: `from src.config import settings` triggers `settings.ensure_directories()` at module level, which creates `data/kb/documents` etc. In Docker containers where data/ is root-owned, this causes `PermissionError`.
- **Fix**: For tests that don't need `settings`, avoid import chains that reach `src.config`. For example, import `OTPManager` directly from the module file instead of through `src.api.auth.__init__` (which re-exports SessionManager → settings). Or use a SimpleOTPManager test double.
- **Broader pattern**: Module-level side effects (like `ensure_directories()`) should be deferred or guarded.

## 2026-03-02: Welcome Emails + Teach Address Documentation

### Docker container selection matters for test sends
- **Problem**: `docker-compose run --rm` containers can't resolve SMTP hostnames (DNS issue). `berengario-email` production image doesn't have volume-mounted source code.
- **Fix**: Use `docker exec berengario-app` for ad-hoc Python scripts — it has volume mounts AND proper DNS.

### Welcome emails should be warm and human, not bullet-point lists
- **Lesson**: First draft was dry bullet points. Users want narrative tone explaining what the system is and how to use it naturally. Use friendly role labels (member/contributor/administrator instead of querier/teacher/admin).

### teach_address vs query_address in email instructions
- **Pattern**: Teaching instructions (CC, BCC, forward) should reference `teach_address` when configured, falling back to `query_address`. Use: `kb_address = teach_address or query_address`.
- **Important**: The `.env` file must actually set `EMAIL_TEACH_ADDRESS` for it to work — code defaults to `None`.
