# Phase 2: Registry Infrastructure - Research

**Researched:** 2026-03-12
**Domain:** Python plugin registry pattern with lazy registration
**Confidence:** HIGH

## Summary

This phase replaces the current hardcoded `isinstance` dispatch in `_translators.py` and `_drivers.py` with a runtime registry that supports both built-in backends (lazy-registered on first use) and manually registered backends (via `register_backend()` API). The registry pattern is well-established in Python, and the existing codebase provides clear integration points.

**Primary recommendation:** Create a single `_registry.py` module that holds a global registry dict mapping backend names to `(config_class, translator, driver_path)` tuples. Replace `isinstance` dispatch in `_translators.py` and `_drivers.py` with registry lookups keyed by config class type. Implement lazy built-in registration triggered when `create_pool()` encounters an unregistered config class.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- `register_backend(name, config_class, translator, driver_path)` — all parameters explicit
- `driver_path` passed directly to `adbc_driver_manager.dbapi.connect(driver=driver_path, ...)`
- ADBC handles resolution (shared library path, manifest path, or driver name)
- Registered backends always use `adbc_driver_manager.dbapi` path (no dbapi module selection)
- Built-in backends retain their richer behavior (PyPI drivers use their own dbapi when installed)

### Backend naming
- Built-in PyPI drivers: use PyPI package name → `"adbc_driver_snowflake"`, `"adbc_driver_bigquery"`, etc.
- Built-in Foundry drivers: prefix with `__dbc__` → `"__dbc__databricks"`, `"__dbc__clickhouse"`, etc.
- Auto-discovered plugins (Phase 3): use PyPI package name (already unique in ecosystem)
- Manual registrations: user chooses any name, but error if already registered
- No format validation — only duplicate checking at registration time

### Registry integration
- Registry replaces hardcoded dispatch entirely
- `_translators.py`: `translate_config()` queries registry for all backends
- `_drivers.py`: `resolve_driver()` queries registry for driver_path
- All 12 built-in backends go through registry
- Built-ins registered lazily per-backend (when config class first used in `create_pool()`)

### Error handling
- `BackendAlreadyRegisteredError` — duplicate registration attempt
- `BackendNotRegisteredError` — lookup of unregistered backend (message includes name and hint to call `register_backend()`)
- `TypeError` — invalid parameters (None config_class, non-callable translator, etc.) with clear message
- Exception hierarchy:
  - `RegistryError(PoolhouseError)` — base for all registry errors
  - `BackendAlreadyRegisteredError(RegistryError)`
  - `BackendNotRegisteredError(RegistryError)`

### Testing approach
- 5 core test scenarios:
  1. Manual registration works — `register_backend()` with valid params succeeds
  2. Duplicate detection — registering same name twice raises `BackendAlreadyRegisteredError`
  3. Invalid params — passing None config_class raises `TypeError` with clear message
  4. Unregistered backend — `create_pool()` with unregistered config raises `BackendNotRegisteredError`
  5. Built-ins work without registration — observable behavior that built-in configs work out of the box
- Entry point simulation tests deferred to Phase 3
- Dummy backend fixture: minimal (config class + no-op translator returning empty dict)

### Claude's Discretion
- Exact registry module structure and internal APIs
- Import ordering strategy for lazy built-in registration
- Whether to expose registry internals for advanced use cases

### Deferred Ideas (OUT OF SCOPE)
- `list_backends()` utility — removed from requirements (no clear use case, can add later if needed)
- Entry point discovery tests — Phase 3 responsibility
- Rich driver metadata for registered backends (pip_extra, driver_type) — simplified to just driver_path
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| REG-01 | Backend Registry | Registry pattern with dict mapping name → (config_class, translator, driver_path). Reverse lookup by config_class type for dispatch. |
| REG-02 | Manual Registration API | `register_backend(name, config_class, translator, driver_path)` with validation and duplicate detection. |
| REG-03 | Registry Integration | Replace `isinstance` dispatch in `_translators.py` and `_drivers.py` with registry lookups. Lazy built-in registration on first use. |
| TEST-INFRA-01 | Dummy Backend Plugin | Minimal config class + no-op translator fixture for testing registration without real driver. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib | 3.11+ | Registry implementation | No external dependencies needed — pattern uses dict, type, and callable |
| pydantic | (existing) | Config class validation | Already in use for all config classes |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | (existing) | Test framework | All test scenarios |
| unittest.mock | (stdlib) | Mocking for unit tests | Mocking `create_pool` internals |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Custom registry | `importlib.metadata` entry_points | Entry points require package installation; manual registration is simpler for Phase 2. Entry points deferred to Phase 3. |
| Class decorator registration | Explicit `register_backend()` call | Decorator hides registration; explicit call is clearer for plugin authors. |

**Installation:**
No new dependencies required — registry is pure Python stdlib.

## Architecture Patterns

### Recommended Project Structure
```
src/adbc_poolhouse/
├── _registry.py           # NEW: Backend registry (name → config_class, translator, driver_path)
├── _exceptions.py         # MODIFY: Add RegistryError hierarchy
├── _translators.py        # MODIFY: Replace isinstance dispatch with registry lookup
├── _drivers.py            # MODIFY: Replace isinstance dispatch with registry lookup
├── _pool_factory.py       # MODIFY: Trigger lazy registration before resolve/translate
└── __init__.py            # MODIFY: Export register_backend, new exceptions
```

### Pattern 1: Registry with Reverse Lookup
**What:** A global dict mapping backend name to registration data, plus a reverse lookup by config class type.
**When to use:** When dispatch needs to find registration by config class (current architecture).
**Example:**
```python
# _registry.py
from typing import Callable
from adbc_poolhouse._base_config import WarehouseConfig

# Type alias for translator function signature
TranslatorFunc = Callable[[WarehouseConfig], dict[str, str]]

# Registration data: (config_class, translator, driver_path)
_Registration = tuple[type[WarehouseConfig], TranslatorFunc, str]

# Forward lookup: name → registration
_registry: dict[str, _Registration] = {}

# Reverse lookup: config_class → name (for dispatch)
_config_to_name: dict[type[WarehouseConfig], str] = {}


def register_backend(
    name: str,
    config_class: type[WarehouseConfig],
    translator: TranslatorFunc,
    driver_path: str,
) -> None:
    """Register a backend with the registry."""
    if name in _registry:
        raise BackendAlreadyRegisteredError(name)
    if not isinstance(config_class, type):
        raise TypeError(f"config_class must be a class, got {type(config_class).__name__}")
    if not callable(translator):
        raise TypeError(f"translator must be callable, got {type(translator).__name__}")
    
    _registry[name] = (config_class, translator, driver_path)
    _config_to_name[config_class] = name


def get_translator(config: WarehouseConfig) -> TranslatorFunc:
    """Get translator for a config instance."""
    config_type = type(config)
    if config_type not in _config_to_name:
        raise BackendNotRegisteredError(config_type.__name__)
    name = _config_to_name[config_type]
    return _registry[name][1]


def get_driver_path(config: WarehouseConfig) -> str:
    """Get driver_path for a config instance."""
    config_type = type(config)
    if config_type not in _config_to_name:
        raise BackendNotRegisteredError(config_type.__name__)
    name = _config_to_name[config_type]
    return _registry[name][2]
```

### Pattern 2: Lazy Built-in Registration
**What:** Register built-in backends only when their config class is first encountered.
**When to use:** Avoid importing all translator modules at startup; only import what's used.
**Example:**
```python
# _registry.py
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from adbc_poolhouse._base_config import WarehouseConfig

# Map config class to registration function (lazy)
_lazy_registrations: dict[type[WarehouseConfig], Callable[[], None]] = {}


def register_lazy(
    config_class: type[WarehouseConfig],
    registration_func: Callable[[], None],
) -> None:
    """Register a lazy initialization function for a config class."""
    _lazy_registrations[config_class] = registration_func


def ensure_registered(config: WarehouseConfig) -> None:
    """Ensure the backend for a config is registered (lazy trigger)."""
    config_type = type(config)
    if config_type in _config_to_name:
        return  # Already registered
    
    if config_type in _lazy_registrations:
        _lazy_registrations[config_type]()
        # After registration, config_type should be in _config_to_name
        if config_type not in _config_to_name:
            raise BackendNotRegisteredError(config_type.__name__)
        return
    
    raise BackendNotRegisteredError(config_type.__name__)
```

### Pattern 3: Exception Hierarchy
**What:** Custom exceptions inheriting from `PoolhouseError` for consistency.
**When to use:** All registry-related errors.
**Example:**
```python
# _exceptions.py (additions)
class RegistryError(PoolhouseError):
    """Base exception for all registry-related errors."""
    pass


class BackendAlreadyRegisteredError(RegistryError):
    """Raised when attempting to register a backend name that already exists."""
    def __init__(self, name: str) -> None:
        super().__init__(f"Backend '{name}' is already registered")


class BackendNotRegisteredError(RegistryError):
    """Raised when looking up a backend that has not been registered."""
    def __init__(self, config_name: str) -> None:
        super().__init__(
            f"Backend for config type '{config_name}' is not registered. "
            f"Call register_backend() to register a custom backend."
        )
```

### Anti-Patterns to Avoid
- **Import cycles:** Don't import config classes at module level in `_registry.py`. Use `TYPE_CHECKING` and lazy imports.
- **Eager registration:** Don't register all 12 built-ins at import time. Use lazy registration.
- **Thread-unsafe registry:** The registry is a module-level dict. For thread safety, consider `threading.Lock` if concurrent registration is expected (not required for Phase 2).
- **Leaking internals:** Don't expose `_registry` dict directly. Provide controlled access via functions.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Plugin discovery | Custom entry point scanner | `importlib.metadata.entry_points()` (Phase 3) | stdlib solution, well-tested |
| Config validation | Custom validator | pydantic model_validator (existing pattern) | Already in use, consistent |
| Exception messages | Ad-hoc string formatting | Exception class with formatted message | Consistent error messages |

**Key insight:** The registry pattern is simple enough to implement directly without external libraries. The complexity is in the integration points, not the registry itself.

## Common Pitfalls

### Pitfall 1: Import Cycles
**What goes wrong:** `_registry.py` imports config classes, config modules import from `_registry.py` → circular import.
**Why it happens:** Config classes might need to reference registry types.
**How to avoid:** Use `TYPE_CHECKING` block for type hints. Register built-ins lazily via functions, not at module level.
**Warning signs:** `ImportError: cannot import name 'X' from partially initialized module`

### Pitfall 2: Registration Order
**What goes wrong:** Built-in backend registered after manual registration with same name → `BackendAlreadyRegisteredError`.
**Why it happens:** Lazy registration happens on first use, which could be after manual registration.
**How to avoid:** Built-in names use reserved prefixes (`adbc_driver_*`, `__dbc__*`). Document that users should avoid these prefixes.
**Warning signs:** User reports "backend already registered" when they didn't register it.

### Pitfall 3: Missing Lazy Registration
**What goes wrong:** Config class used but never registered → `BackendNotRegisteredError` for built-in.
**Why it happens:** Forgot to add lazy registration entry for a new built-in backend.
**How to avoid:** Centralize lazy registration setup in one place. Test all 12 built-ins work without manual registration.
**Warning signs:** `BackendNotRegisteredError` for `DuckDBConfig` or other built-in.

### Pitfall 4: Translator Signature Mismatch
**What goes wrong:** Registered translator doesn't match expected `Callable[[WarehouseConfig], dict[str, str]]`.
**Why it happens:** Plugin author defines translator with wrong signature.
**How to avoid:** Validate translator is callable at registration time. TypeError with clear message if not.
**Warning signs:** `TypeError` at registration time, or runtime error when translator is called.

## Code Examples

### Registration API (public)
```python
# __init__.py (additions to exports)
from adbc_poolhouse._registry import register_backend
from adbc_poolhouse._exceptions import (
    BackendAlreadyRegisteredError,
    BackendNotRegisteredError,
    RegistryError,
)

__all__ = [
    # ... existing exports ...
    "register_backend",
    "RegistryError",
    "BackendAlreadyRegisteredError",
    "BackendNotRegisteredError",
]
```

### Modified translate_config (dispatch replacement)
```python
# _translators.py (modified)
from adbc_poolhouse._registry import ensure_registered, get_translator

def translate_config(config: WarehouseConfig) -> dict[str, str]:
    """Translate any supported warehouse config to ADBC driver kwargs."""
    ensure_registered(config)  # Trigger lazy registration if needed
    translator = get_translator(config)
    return translator(config)
```

### Modified resolve_driver (dispatch replacement)
```python
# _drivers.py (modified)
from adbc_poolhouse._registry import ensure_registered, get_driver_path

def resolve_driver(config: WarehouseConfig) -> str:
    """Resolve the ADBC driver path or short name for a warehouse config."""
    ensure_registered(config)  # Trigger lazy registration if needed
    return get_driver_path(config)
```

### Lazy Built-in Registration Setup
```python
# _registry.py (built-in setup)
def _setup_lazy_registrations() -> None:
    """Register lazy initialization for all built-in backends."""
    # PyPI drivers
    register_lazy(DuckDBConfig, lambda: _register_duckdb())
    register_lazy(SnowflakeConfig, lambda: _register_snowflake())
    # ... etc for all 12 built-ins


def _register_duckdb() -> None:
    """Lazy registration for DuckDB."""
    from adbc_poolhouse._duckdb_config import DuckDBConfig
    from adbc_poolhouse._duckdb_translator import translate_duckdb
    
    register_backend(
        "adbc_driver_duckdb",  # Note: DuckDB is special, uses _duckdb path
        DuckDBConfig,
        translate_duckdb,
        _resolve_duckdb_path(),  # Or defer resolution to connect time
    )


def _register_snowflake() -> None:
    """Lazy registration for Snowflake."""
    from adbc_poolhouse._snowflake_config import SnowflakeConfig
    from adbc_poolhouse._snowflake_translator import translate_snowflake
    
    register_backend(
        "adbc_driver_snowflake",
        SnowflakeConfig,
        translate_snowflake,
        "adbc_driver_snowflake",  # Package name for manifest resolution
    )
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Hardcoded `isinstance` dispatch | Registry lookup | Phase 2 | Extensible, supports plugins |
| All translators imported at module level | Lazy import on first use | Phase 2 | Faster startup, less memory |

**Deprecated/outdated:**
- `_PYPI_PACKAGES` dict in `_drivers.py`: Replaced by registry entries
- `_FOUNDRY_DRIVERS` dict in `_drivers.py`: Replaced by registry entries
- `isinstance` chain in `translate_config()`: Replaced by registry lookup

## Open Questions

1. **Should `resolve_dbapi_module()` also go through the registry?**
   - What we know: CONTEXT.md says "Registered backends always use `adbc_driver_manager.dbapi` path"
   - What's unclear: Built-in PyPI drivers still need their own dbapi module when installed
   - Recommendation: Keep `resolve_dbapi_module()` logic separate for built-ins; registered backends always use `adbc_driver_manager.dbapi`

2. **Should the registry store dbapi_module info for built-ins?**
   - What we know: Built-in PyPI drivers have richer behavior (own dbapi when installed)
   - What's unclear: How to represent this in the registry without complicating the API
   - Recommendation: Keep dbapi_module resolution in `_drivers.py` for built-ins only. Registered backends don't need this.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (existing) |
| Config file | `pyproject.toml` [tool.pytest] |
| Quick run command | `uv run pytest tests/test_registry.py -x` |
| Full suite command | `uv run pytest` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| REG-01 | Backend registry stores and retrieves registration data | unit | `uv run pytest tests/test_registry.py::TestBackendRegistry -x` | ❌ Wave 0 |
| REG-02 | `register_backend()` validates params and detects duplicates | unit | `uv run pytest tests/test_registry.py::TestRegisterBackend -x` | ❌ Wave 0 |
| REG-03 | Registry replaces isinstance dispatch in translators/drivers | unit | `uv run pytest tests/test_registry.py::TestRegistryIntegration -x` | ❌ Wave 0 |
| TEST-INFRA-01 | Dummy backend fixture for testing | fixture | `uv run pytest tests/test_registry.py::TestDummyBackend -x` | ❌ Wave 0 |

### Test Scenarios (from CONTEXT.md)
| # | Scenario | Test Class | Key Assertions |
|---|----------|------------|----------------|
| 1 | Manual registration works | `TestRegisterBackend::test_valid_registration` | No exception raised, registry contains entry |
| 2 | Duplicate detection | `TestRegisterBackend::test_duplicate_raises` | `BackendAlreadyRegisteredError` raised |
| 3 | Invalid params | `TestRegisterBackend::test_invalid_params` | `TypeError` with clear message |
| 4 | Unregistered backend | `TestRegistryIntegration::test_unregistered_config` | `BackendNotRegisteredError` from `create_pool()` |
| 5 | Built-ins work without registration | `TestBuiltInBackends::test_duckdb_without_manual_registration` | `create_pool(DuckDBConfig())` succeeds |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_registry.py -x`
- **Per wave merge:** `uv run pytest`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_registry.py` — covers REG-01, REG-02, REG-03, TEST-INFRA-01
- [ ] Dummy backend fixture in `tests/conftest.py` — minimal config class + no-op translator
- [ ] Exception hierarchy tests in `tests/test_exceptions.py` (or add to existing)

### Key Integration Points to Test
1. **`create_pool()` → `ensure_registered()`**: Verify lazy registration triggered
2. **`translate_config()` → `get_translator()`**: Verify correct translator returned
3. **`resolve_driver()` → `get_driver_path()`**: Verify correct driver_path returned
4. **Exception messages**: Verify `BackendNotRegisteredError` includes hint to call `register_backend()`

## Sources

### Primary (HIGH confidence)
- Existing codebase analysis: `_translators.py`, `_drivers.py`, `_pool_factory.py`, `_exceptions.py`
- CONTEXT.md locked decisions — user-verified requirements

### Secondary (MEDIUM confidence)
- Python stdlib patterns for registry/plugin architecture (well-established patterns)

### Tertiary (LOW confidence)
- None — all findings based on existing codebase analysis

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — No new dependencies, pure Python stdlib
- Architecture: HIGH — Pattern is well-established, existing code provides clear integration points
- Pitfalls: HIGH — Based on common Python import/registration patterns

**Research date:** 2026-03-12
**Valid until:** 2026-04-12 (stable patterns, no external dependencies)
