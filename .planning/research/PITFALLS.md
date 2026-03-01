# PITFALLS — adbc-poolhouse v1.1.0 Milestone

**Research Type:** Project Research — Pitfalls for specific v1.1.0 changes
**Milestone:** v1.1.0 — Backend Expansion & Debt Cleanup
**Date:** 2026-03-01
**Scope:** Four targeted risk areas: Teradata driver field names, Databricks dual-mode
translator, dead abstract method removal, and justfile `dbc` CLI tooling recipes

---

## How to Read This Document

Each pitfall covers:
- **What goes wrong**: the specific failure mode in this codebase
- **Why it happens**: root cause
- **Consequences**: what breaks
- **Prevention**: concrete steps with code references
- **Detection**: warning signs
- **Phase**: which milestone phase should address it

Pitfalls are grouped by the four v1.1.0 risk areas, then ordered critical → moderate → minor
within each group.

---

## Risk Area 1: Teradata ADBC Driver Field Names

### Context

Teradata was implemented (`.pyc` files present for `_teradata_config.py` and
`_teradata_translator.py`), then removed during v0.1 cleanup because no ADBC driver existed
in the Foundry at that time. v1.1.0 re-adds Teradata support. The v0.1 audit flagged field
names as "LOW confidence — triangulated from non-authoritative sources; real driver docs
returned 404 at research time."

As of 2026-03-01, docs.adbc-drivers.org does **not** list a Teradata driver among its eight
available drivers (ClickHouse, Redshift, BigQuery, Databricks, MSSQL, MySQL, Snowflake,
Trino). No Teradata driver appears in the Foundry. The authoritative source for any Teradata
ADBC driver, if one emerges, would be docs.adbc-drivers.org or the `adbc-drivers` GitHub
organisation.

---

### PITFALL-T1: Teradata ADBC driver does not exist — implementing against it will produce dead code (CRITICAL)

**What goes wrong:**
v1.1.0 lists "verify Teradata field names" as an active task. But as of research date, there
is no Teradata driver in the ADBC Driver Foundry. Implementing `TeradataConfig` and
`translate_teradata()` against inferred or ODBC-derived field names (host, username, password,
database) will produce dead code that cannot be tested against a real driver. When a real
driver eventually ships, its field names may differ from any ODBC/JDBC parameter names.

**Why it happens:**
Teradata's existing ODBC/JDBC drivers use parameter names like `Host`, `Username`, `Password`,
`Database`, `DBS_PORT`. The Columnar ADBC drivers for other warehouses use their own field
name conventions (e.g. MSSQL uses `uri`, `host`, `username`, `password`, `database`,
`trustServerCertificate`). There is no guarantee Teradata ADBC will match ODBC parameter
names — the Databricks ADBC driver, for instance, uses only `uri` with no separate `host` or
`http_path` fields, contrary to what ODBC/JDBC docs suggest.

**Consequences:**
- Silent wrong-key bugs: driver ignores unknown kwargs silently, so tests pass but connection
  fails at runtime with a cryptic auth or "not connected" error rather than "unknown parameter"
- Dead code committed as "verified": every future maintainer must re-verify the same fields
  when the real driver ships, and the wrong names will have spread into tests, docs, and type
  stubs

**Prevention:**
Do not implement TeradataConfig or translate_teradata() in v1.1.0. Monitor
docs.adbc-drivers.org for a Teradata entry. When a driver ships:
1. Install it locally via `dbc install teradata`
2. Inspect the driver's manifest or source for the parameter schema
3. Connect with a minimal kwargs dict and iterate — wrong keys produce errors or are silently
   ignored, so test with `host` vs `Host` vs `hostname` explicitly

**Detection:**
Check docs.adbc-drivers.org/drivers/index.html before starting any Teradata work. If Teradata
is not listed, block the task. The `.pyc` files
(`_teradata_config.cpython-314.pyc`, `_teradata_translator.cpython-314.pyc`) in
`__pycache__` are stale artefacts from the pre-v0.1 implementation and should be cleaned up;
their presence does not indicate the source files still exist.

**Phase:** Teradata tech debt task — defer entirely until driver is listed on
docs.adbc-drivers.org. If this milestone proceeds under the assumption that a driver exists,
this is the first gate to check.

---

### PITFALL-T2: Confusing Teradata ODBC/JDBC parameter names with ADBC field names (MODERATE)

**What goes wrong:**
If Teradata ADBC does ship during v1.1.0, a developer may reach for the Teradata JDBC/ODBC
documentation (`Host`, `DBS_PORT`, `Username`, `Password`, `Database`) and assume these map
directly to ADBC `db_kwargs` keys. The existing pattern in this codebase (`_mssql_translator.py`)
uses lowercase `host`, `username`, `password`, `database` for decomposed fields — but this was
itself flagged as LOW confidence (`# LOW confidence key name` on every key). The MSSQL driver
quickstart uses a URI-only pattern; the decomposed-field key names were never verified against a
live driver.

**Why it happens:**
The codebase has an established pattern of URI-first with decomposed-field fallback
(see `_mssql_translator.py`). A developer adding Teradata will copy this pattern and guess at
field names. Columnar's Teradata driver, if it follows the same convention as their other
drivers, likely uses URI-only — matching the Databricks pattern, not the MSSQL decomposed
pattern.

**Prevention:**
If Teradata ADBC becomes available: start with URI-only (`uri` key only, mirroring
`_databricks_translator.py`) and verify with a live connection before adding decomposed fields.
Use `# VERIFIED from dbc install teradata + live test` comments on any accepted key names,
matching the verification comment style in `_snowflake_translator.py` and
`_databricks_translator.py`.

**Detection:**
Any `# LOW confidence` comment on a key name in a translator is a flag. The v0.1 audit
already identified `_mssql_translator.py` decomposed-field key names as unverified. Any new
Teradata translator that copies those names inherits the same LOW confidence.

**Phase:** Teradata implementation phase (whenever that occurs, not v1.1.0).

---

## Risk Area 2: Fixing Databricks Translator — URI and Decomposed-Field Dual Mode

### Context

`translate_databricks()` currently returns an empty dict when `config.uri is None`, despite
`DatabricksConfig` having `host`, `http_path`, `token`, and other individual fields.
The docstring on `DatabricksConfig` now correctly says "Connection must be specified as a
full URI. Individual fields... are stored for potential future decomposed-field translation
but are not currently passed to the driver." The v1.1.0 task is to fix this so decomposed
fields are actually translated.

**Critical finding from research:** The Columnar ADBC Databricks driver (docs.adbc-drivers.org)
is URI-only. There is no documented support for separate `host`, `http_path`, `token` kwargs.
The driver accepts exactly one `db_kwargs` key: `uri`. The URI format is:
`databricks://token:<token>@<hostname>:443/<http-path>` for PAT auth, or query-param variants
for OAuth.

This changes the nature of the fix: "decomposed-field support" means **constructing a URI from
the decomposed fields in the translator**, not passing them as separate kwargs.

---

### PITFALL-D1: Constructing the URI from decomposed fields requires URL-encoding (CRITICAL)

**What goes wrong:**
The Databricks driver docs state: "Reserved characters in URI elements must be URI-encoded.
For example, `@` becomes `%40`." PAT tokens frequently contain characters that are URL
metacharacters: `+`, `/`, `=` (base64 alphabet), and occasionally `@`, `#`, `?`.
If `translate_databricks()` constructs a URI with `f"databricks://token:{token}@{host}:443/{http_path}"`
without encoding `token`, a token like `dapi123+abc=xyz` produces an invalid URI that the
driver silently misparses.

**Why it happens:**
Python f-strings do no URL encoding. `urllib.parse.quote()` is the correct tool but the
`safe` parameter must be calibrated: `quote(token, safe="")` (no safe chars) for the
token segment; `quote(http_path, safe="/")` (preserve slashes) for the path segment.

**Consequences:**
- Connection silently fails with an authentication error, not an encoding error
- The failure is environment-specific: tokens without special characters work fine; tokens
  with `+` or `=` fail — often a production vs. development discrepancy if dev tokens are
  simpler

**Prevention:**
Use `urllib.parse.quote()` for every variable component of the constructed URI:
```python
from urllib.parse import quote

token_enc = quote(token_str, safe="")
host_enc = quote(host_str, safe="")  # hostnames are safe but be explicit
path_enc = quote(http_path_str, safe="/")  # preserve slash separators
uri = f"databricks://token:{token_enc}@{host_enc}:443/{path_enc}"
```
Write a unit test that round-trips a token containing `+`, `=`, `@`, and `/` through the
translator and verifies the URI is parseable by `urllib.parse.urlparse()` without loss.

**Detection:**
Test with a PAT token that is exactly `dapi+test=value/path`. A correct implementation
produces a URI that `urlparse` decodes back to the original token.

**Phase:** Databricks fix phase.

---

### PITFALL-D2: Silent empty dict when neither URI nor required decomposed fields are set (CRITICAL)

**What goes wrong:**
The current `translate_databricks()` returns `{}` when `config.uri is None`. After the fix,
the decomposed-field path also produces `{}` if `config.host` is None (since host, http_path,
and token are all Optional). The pool factory calls `create_adbc_connection(driver_path, {})`
which attempts to connect with no credentials — the driver will raise a cryptic error (likely
"no URI provided" or a network error attempting to connect to nothing) rather than a clear
"misconfigured" message.

**Why it happens:**
`DatabricksConfig` was designed with all fields Optional to allow env-var-only configuration.
Valid configurations are: (a) URI set, or (b) host + http_path + token set. Invalid: all None.
The translator has no validation gate.

**Consequences:**
- Misconfigured consumers get a driver-level error instead of a library-level `ConfigurationError`
- The error surface shifts from config construction time (where Pydantic validates) to
  `create_pool()` call time with a cryptic driver message

**Prevention:**
Add a Pydantic `model_validator(mode="after")` to `DatabricksConfig` that raises `ValueError`
if neither `uri` nor the minimum decomposed fields (`host` + `http_path` + `token`) are set:
```python
@model_validator(mode="after")
def _require_uri_or_decomposed(self) -> "DatabricksConfig":
    has_uri = self.uri is not None
    has_decomposed = (
        self.host is not None
        and self.http_path is not None
        and self.token is not None
    )
    if not has_uri and not has_decomposed:
        raise ValueError(
            "DatabricksConfig requires either 'uri' or all of "
            "'host', 'http_path', and 'token'"
        )
    return self
```
Also add a guard in `translate_databricks()` that raises `ConfigurationError` (not `ValueError`)
if both paths produce empty output — defence in depth.

**Detection:**
Unit test: `DatabricksConfig()` with all fields at None should raise `ValidationError`, not
silently construct. The existing test suite almost certainly lacks this test since the feature
was not implemented.

**Phase:** Databricks fix phase.

---

### PITFALL-D3: URI takes precedence over decomposed fields — but this must be explicit (MODERATE)

**What goes wrong:**
After the fix, both `uri` and decomposed fields could be set simultaneously (e.g. a user sets
`DATABRICKS_URI` in the environment AND `DATABRICKS_HOST`). The translator must have a
documented precedence rule. The existing MSSQL pattern (`_mssql_translator.py` line 24-26) uses
`if config.uri is not None: return kwargs` — URI wins and decomposed fields are silently ignored.
If the user provided both intending them to "merge" (e.g. URI for base connection, `token` as
override), the silent discard surprises them.

**Why it happens:**
The URI-first pattern is correct for Databricks because the driver is URI-only — you cannot pass
`host` as a separate kwarg alongside a `uri`. But the precedence rule must be documented both
in the docstring and enforced by a `model_validator` warning or validation error.

**Prevention:**
Add a `model_validator(mode="after")` that warns (or raises) if both `uri` and any decomposed
field are non-None. A `UserWarning` is more DX-friendly than a hard error here. Document the
precedence rule in the class docstring and in `translate_databricks()` with a comment:
`# URI-first: when both uri and decomposed fields are set, uri takes precedence.`

**Detection:**
Unit test: `DatabricksConfig(uri="databricks://...", host="conflict.azuredatabricks.net")`
should trigger a warning. Verify the warning fires via `pytest.warns(UserWarning)`.

**Phase:** Databricks fix phase.

---

### PITFALL-D4: http_path leading slash handling (MODERATE)

**What goes wrong:**
Databricks HTTP paths take the form `/sql/1.0/warehouses/abc123`. The URI format embeds this
after the port: `databricks://token:...@host:443/sql/1.0/warehouses/abc123`. If a user
provides `http_path="/sql/1.0/warehouses/abc123"` (with leading slash) the constructed URI
becomes `databricks://token:...@host:443//sql/...` (double slash). If they provide without
leading slash (`sql/1.0/warehouses/abc123`) the URI is correct. Both forms are plausible
user inputs.

**Why it happens:**
f-string URI construction is not slash-aware. `urllib.parse.urljoin` normalises this but
`urljoin` semantics are not straightforward with opaque schemes like `databricks://`.

**Prevention:**
Normalise in the translator: `http_path.lstrip("/")` before embedding in the URI. Add a unit
test with both `"/sql/1.0/..."` and `"sql/1.0/..."` forms and assert identical URI output.
Document in `DatabricksConfig.http_path` docstring: "Leading slash is optional and normalised."

**Detection:**
A double-slash URI (`databricks://...@host:443//sql/...`) causes a driver parse error that
manifests as a network or auth failure rather than a URI error.

**Phase:** Databricks fix phase.

---

### PITFALL-D5: OAuth M2M decomposed mode is not supported by this approach (MINOR)

**What goes wrong:**
OAuth M2M authentication (`authType=OAuthM2M&clientID=...&clientSecret=...`) is expressed
as URI query parameters in the Databricks driver. The decomposed-field path builds a PAT
URI (`token:<token>@<host>`). Constructing an OAuth M2M URI from decomposed fields requires
a different URI template: `databricks://<host>:443/<http-path>?authType=OAuthM2M&clientID=...`.
If the translator always emits the PAT template when host+http_path+token are set, an OAuth
M2M user who sets `auth_type="OAuthM2M"`, `client_id`, and `client_secret` instead of `token`
will get an incorrect URI with `token:None@...` or an exception.

**Prevention:**
Add a branch in the decomposed-field path that inspects `config.auth_type` and selects the
appropriate URI template. For now, limit the decomposed-field path to PAT auth only (host +
http_path + token) and raise `ValueError` if `auth_type` is set alongside decomposed fields,
directing the user to provide a full `uri` instead. Document this limitation clearly.

**Detection:**
Unit test: setting `auth_type="OAuthM2M"` with decomposed fields and no URI should raise a
clear error, not produce a malformed URI.

**Phase:** Databricks fix phase.

---

## Risk Area 3: Removing Dead Abstract Methods from BaseWarehouseConfig Hierarchy

### Context

The v0.1 audit identified `_adbc_driver_key()` as a dead abstract method on
`BaseWarehouseConfig` implemented in all 10 config subclasses but never called by `_drivers.py`
or `_translators.py` (superseded by the isinstance dispatch-table approach). The audit also
flagged `AdbcCreatorFn` as a dead type alias in `_pool_types.py`.

**Current state (confirmed by reading source):** Both are already removed. `_base_config.py`
shows no abstract methods — `_adbc_driver_key()` is gone. `_pool_types.py` does not exist.
The `.continue-here.md` confirms both were deleted in the v0.1 pre-release cleanup session.

The pitfalls below apply if the PROJECT.md active task list still shows these as open
(it does, as of 2026-02-28), which means either the project file is stale, or a re-addition
is planned. Regardless, these pitfalls document what would break if such removals were
executed on a live hierarchy.

---

### PITFALL-R1: Protocol structural check still requires the method if WarehouseConfig Protocol references it (CRITICAL)

**What goes wrong:**
`WarehouseConfig` in `_base_config.py` is a `@runtime_checkable Protocol`. When a protocol
method is removed from the Protocol definition, any existing `isinstance(config, WarehouseConfig)`
check in the codebase will no longer verify that the method exists. This is correct behaviour —
but the inverse is dangerous: if the Protocol is updated to remove a method that *was* being
relied upon structurally, callers using structural typing assumptions break silently.

In this codebase specifically: `_adbc_entrypoint()` is declared on both the Protocol
(`WarehouseConfig`) and `BaseWarehouseConfig`. If a future removal mistakenly targets
`_adbc_entrypoint()` instead of the already-removed `_adbc_driver_key()`, the Protocol
becomes structurally weaker and callers using `isinstance(config, WarehouseConfig)` no longer
verify the method is present.

**Why it happens:**
`_adbc_driver_key()` and `_adbc_entrypoint()` have similar naming patterns. A developer
removing dead methods may target the wrong one, especially if working from the v0.1 audit
which named `_adbc_driver_key()` but not `_adbc_entrypoint()`.

**Prevention:**
Before removing any method from `BaseWarehouseConfig` or `WarehouseConfig`:
1. Grep the entire codebase for the method name: `grep -r "_adbc_driver_key\|_adbc_entrypoint" src/ tests/`
2. Verify the method is absent from `WarehouseConfig` Protocol before attempting removal from
   subclasses
3. Confirm `_pool_factory.py` actually calls `config._adbc_entrypoint()` (line 76) — this is
   live, not dead

**Detection:**
`basedpyright --strict` will catch any call to a removed method. Run type checking before
and after the removal with zero new errors as the acceptance criterion.

**Phase:** Tech debt cleanup phase. Given both items are already removed from the current
source, this pitfall applies if the PROJECT.md task list is stale and the removal is attempted
again — the defence is to check the live source before acting.

---

### PITFALL-R2: Subclass `__init__` may rely on the abstract method as a construction hook (MODERATE)

**What goes wrong:**
In Python's ABC system, an abstract method on a `BaseSettings` subclass that has been
implemented across 10 subclasses may be used as a construction-time hook by some subclasses.
If `_adbc_driver_key()` returns a string used inside the subclass's own `__init__` or
`model_validator`, removing the abstract method from the base does not remove the
implementations — but removing the implementations from each subclass would break any such
usage.

**Why it happens:**
In this codebase, the 10 subclasses each implemented `_adbc_driver_key()` returning a simple
string literal (e.g. `return "snowflake"`). No model validator or `__init__` called it — the
dispatch table in `_drivers.py` used `isinstance` instead. But a copy-paste error in a new
subclass (added during v1.1.0) could re-introduce `_adbc_driver_key()` in a subclass if the
developer consults the old phase-03 plan documents rather than the current source.

**Prevention:**
When adding a new backend in v1.1.0: use the current `_drivers.py` dispatch-table pattern
(adding to `_PYPI_PACKAGES` or `_FOUNDRY_DRIVERS` dicts) as the template, not the phase-03
plan documents which predate the dispatch-table refactor. Do not add `_adbc_driver_key()` to
any new config class.

**Detection:**
`grep -r "_adbc_driver_key" src/` should return zero results. Any result is a regression.

**Phase:** All new backend phases in v1.1.0.

---

### PITFALL-R3: Pydantic v2 field shadowing when a concrete class re-adds a removed method as a `@property` (MODERATE)

**What goes wrong:**
If a developer removes `_adbc_driver_key()` as an abstract method but then tries to re-add
it as a `@computed_field` or `@property` on a subclass (e.g. to expose the driver name for
debugging), Pydantic v2 raises a validation error: "field name shadows an attribute in the
parent class." This is a known Pydantic v2 issue (GitHub issue #10587, #11939). The error
message is confusing because it refers to "field name" but the conflict is with a method.

**Why it happens:**
Pydantic v2's metaclass intercepts class attribute definition. A property named
`_adbc_driver_key` on a subclass conflicts with Pydantic's internal attribute tracking even
if the base class has no such attribute. The leading underscore does not protect it.

**Prevention:**
Do not add `_adbc_driver_key` as a property or computed field on any config subclass.
If driver-name introspection is needed for a new feature, add a separate public method (e.g.
`driver_name()`) or expose it through the `_FOUNDRY_DRIVERS` / `_PYPI_PACKAGES` lookup tables
in `_drivers.py`.

**Detection:**
`pydantic.ValidationError: field name shadows an attribute` at class definition time
(import time for the module). This is caught by any test that imports the affected config class.

**Phase:** Any phase adding new config subclasses in v1.1.0.

---

## Risk Area 4: Justfile Recipes Shelling Out to `dbc` CLI

### Context

v1.1.0 adds justfile recipes for Foundry driver management: install the `dbc` CLI itself,
then install and verify supported Foundry drivers. The existing justfile has two recipes
(`build`, `serve`) that shell out to `uv` — a tool that is always present in this project's
dev environment. The new recipes will shell out to `dbc`, which must be installed separately
and is not a uv dependency.

The `dbc` CLI is installed via `curl -LsSf https://dbc.columnar.tech/install.sh | sh`, which
installs to `~/.cargo/bin/dbc` (or similar) and requires PATH configuration. Its installation
path is not guaranteed to be in `$PATH` when a `just` recipe runs.

---

### PITFALL-J1: `dbc` not in PATH when just recipe runs — opaque failure (CRITICAL)

**What goes wrong:**
When a recipe calls `dbc install databricks` and `dbc` is not in PATH, `just` invokes sh
which exits with code 127 ("command not found"). The error message is:
`error: Recipe 'install-drivers' failed on line X with exit code 127`
This says nothing about `dbc` not being installed. A developer unfamiliar with the setup
sees a just error, not a prerequisite error.

**Why it happens:**
`just` does not perform dependency checks before running recipes. It passes recipe body lines
to sh. If the first command fails (exit 127), just stops and reports the recipe failure with
the exit code — the sh output ("sh: dbc: command not found") may or may not be visible
depending on terminal buffering.

**Prevention:**
Add an explicit prerequisite check at the top of every recipe that invokes `dbc`:
```just
# Install all supported Foundry drivers
install-drivers:
    #!/usr/bin/env bash
    set -euo pipefail
    if ! command -v dbc &>/dev/null; then
        echo "ERROR: 'dbc' CLI is not installed or not in PATH."
        echo "Install it with: curl -LsSf https://dbc.columnar.tech/install.sh | sh"
        echo "Then add it to your PATH and re-run: just install-drivers"
        exit 1
    fi
    dbc install databricks redshift trino mssql
```
The `command -v` check produces a human-readable error pointing to the install command.
Do not use `just`'s `which()` function for this — it evaluates at parse time against the
parent process PATH, not the recipe execution PATH (see PITFALL-J3 below).

**Detection:**
Run `just install-drivers` in a clean shell where `dbc` is not installed. The error should
be actionable ("install with..."), not opaque ("exit code 127").

**Phase:** Foundry driver tooling phase.

---

### PITFALL-J2: `dbc install` is idempotent but `dbc` version matters — no version check (MODERATE)

**What goes wrong:**
`dbc install databricks` installs the latest available driver version. If the recipe is run
on a machine where `dbc` is installed but outdated (e.g. `dbc` 0.1.x vs 0.2.x), the
driver install may fail with a "registry version mismatch" or silently install an incompatible
driver version. `dbc 0.2.0` introduced new features (pre-releases, private registries); a
recipe written for 0.2.0 semantics may fail silently on 0.1.x.

**Prevention:**
Add a version check before driver installation:
```just
install-drivers:
    #!/usr/bin/env bash
    set -euo pipefail
    if ! command -v dbc &>/dev/null; then
        echo "ERROR: 'dbc' is not installed. See: https://dbc.columnar.tech"
        exit 1
    fi
    # Warn if dbc version is older than 0.2.0
    dbc_version=$(dbc --version 2>&1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
    echo "dbc version: ${dbc_version}"
    dbc install databricks redshift trino mssql
```
The version is logged but not enforced — a warning is enough for now. If `dbc --version`
output format changes, the grep fails silently rather than aborting the recipe (acceptable).

**Detection:**
Run `just install-drivers` with an old `dbc` version. If the version logging fails (wrong
grep pattern), the recipe continues — which is the desired graceful degradation.

**Phase:** Foundry driver tooling phase.

---

### PITFALL-J3: `just`'s `which()` function evaluates at parse time, not recipe execution time (MODERATE)

**What goes wrong:**
`just` provides a built-in `which()` function (e.g. `DBC := which("dbc")`). If `dbc` is
not in the parent shell's PATH when `just` is invoked but IS in PATH inside the recipe
(e.g. because the recipe exports a modified PATH), `which()` returns empty string at parse
time and any recipe that uses `DBC` gets an empty variable.

This is documented in the `just` issue tracker (issue #2597): "`which()` only accesses the
parent process's environment variables, not modified exports within the same scope." Exports
inside justfile variables (`export PATH := ...`) do not affect `which()` evaluation.

**Why it happens:**
`just` evaluates all variable assignments and function calls before running any recipe body.
`which()` is a parse-time function. Recipes run in a subprocess where PATH modifications are
visible, but that subprocess is created after `which()` has already been evaluated.

**Prevention:**
Do not use `just`'s `which()` to check for `dbc`. Use `command -v dbc` inside shebang recipes
(`#!/usr/bin/env bash`) where the full recipe body runs in a single shell process that sees
the current PATH. This is why PITFALL-J1's prevention code uses `command -v` inside a
shebang recipe rather than a top-level justfile variable.

**Detection:**
A recipe that sets `DBC := which("dbc")` and then calls `{{DBC}} install ...` will silently
execute an empty command (` install ...`) when `dbc` is not in the parent PATH. The shell
error "sh: : command not found" (empty command name) is more confusing than "dbc: command
not found."

**Phase:** Foundry driver tooling phase.

---

### PITFALL-J4: Driver install path not in `adbc_driver_manager` search path — `dbc install` succeeds but driver not found at runtime (MODERATE)

**What goes wrong:**
`dbc install databricks` installs the driver to one of three locations depending on which
environment variables are set:
- `$ADBC_DRIVER_PATH` if set
- `$VIRTUAL_ENV/etc/adbc/drivers/` if inside a virtualenv
- `$CONDA_PREFIX/etc/adbc/drivers/` if inside conda
- `~/.config/adbc/drivers/` (Linux) or `~/Library/Application Support/ADBC/Drivers/` (macOS)
  as the user-level fallback

`adbc_driver_manager` (the Python library) searches the same locations to discover driver
manifests. But the codebase's test suite runs inside a uv virtualenv (`uv run pytest`).
If `dbc install` was run without the virtualenv active (or with a different `VIRTUAL_ENV`),
the driver installs to the user-level path but the Python process running under uv looks in
`$VIRTUAL_ENV/etc/adbc/drivers/` first. The driver is installed but not found.

**Why it happens:**
`dbc install --level user` is the documented default when run outside a virtualenv. If a
developer runs `just install-drivers` from a plain terminal (not the uv-activated venv),
`dbc` installs to `~/.config/adbc/drivers/` but `uv run python` uses
`$VIRTUAL_ENV/etc/adbc/drivers/` as the priority search location. The manifest exists but
in the wrong location.

**Prevention:**
Recipes that install Foundry drivers should explicitly target the virtualenv level:
```just
install-drivers:
    #!/usr/bin/env bash
    set -euo pipefail
    if ! command -v dbc &>/dev/null; then
        echo "ERROR: 'dbc' is not installed."
        exit 1
    fi
    # Install at the virtualenv level so uv run python finds the drivers
    dbc install --level env databricks redshift trino mssql
```
`--level env` causes `dbc` to read `VIRTUAL_ENV` or `CONDA_PREFIX` and install there.
Include a README note: "Run `just install-drivers` from within the uv virtualenv
(`uv run just install-drivers`) or after `source .venv/bin/activate`."

**Detection:**
After `just install-drivers`, run `uv run python -c "import adbc_driver_manager; adbc_driver_manager.dbapi.connect('databricks')"`.
A `NOT_FOUND` error after a successful install indicates the path mismatch.

**Phase:** Foundry driver tooling phase. This is also a runtime integration test concern —
any integration test that tests Foundry driver loading should run under `uv run` and verify
the driver is discoverable before asserting connection behaviour.

---

### PITFALL-J5: Verify recipe cannot distinguish "driver installed and working" from "driver installed but broken" (MINOR)

**What goes wrong:**
A "verify drivers" recipe might call `dbc list` or check for the manifest file's existence.
But existence of the manifest file does not mean the shared library loads correctly. A
corrupted download or architecture mismatch (e.g. x86_64 driver on arm64 macOS) produces a
manifest that `adbc_driver_manager` finds but fails to `dlopen()`. The verify recipe passes
but `create_pool()` still raises `NOT_FOUND` or a `dlopen` error.

**Prevention:**
The verify recipe should attempt a minimal Python import via `adbc_driver_manager` rather than
checking file existence:
```just
verify-drivers:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "Verifying Foundry drivers are loadable..."
    uv run python -c "
import adbc_driver_manager
for driver in ['databricks', 'redshift', 'trino', 'mssql']:
    try:
        # Attempt to load the driver (will fail auth but not load)
        adbc_driver_manager.dbapi.connect(driver)
    except adbc_driver_manager.Error as e:
        status = getattr(e, 'status_code', None)
        if hasattr(adbc_driver_manager, 'AdbcStatusCode'):
            not_found = adbc_driver_manager.AdbcStatusCode.NOT_FOUND
            if status == not_found or 'NOT_FOUND' in str(e):
                print(f'FAIL: {driver} not found')
                exit(1)
        print(f'OK: {driver} loaded (auth failure expected without credentials)')
    except Exception:
        print(f'OK: {driver} loaded (auth failure expected without credentials)')
print('All drivers loadable.')
"
```
This pattern distinguishes `NOT_FOUND` (driver absent) from auth/connection errors (driver
present but no credentials) — exactly the same pattern already used in `_driver_api.py`.

**Detection:**
After a broken driver installation: `just verify-drivers` should fail, not pass.

**Phase:** Foundry driver tooling phase.

---

## Phase Assignment Summary

| Pitfall | Risk Area | Phase | Severity |
|---------|-----------|-------|----------|
| PITFALL-T1: Teradata driver does not exist | Teradata | Before any Teradata work | CRITICAL |
| PITFALL-T2: ODBC vs ADBC field name confusion | Teradata | Teradata implementation | MODERATE |
| PITFALL-D1: URL-encoding in constructed URI | Databricks | Databricks fix | CRITICAL |
| PITFALL-D2: Silent empty dict — no validation gate | Databricks | Databricks fix | CRITICAL |
| PITFALL-D3: URI/decomposed precedence undocumented | Databricks | Databricks fix | MODERATE |
| PITFALL-D4: http_path double-slash from leading slash | Databricks | Databricks fix | MODERATE |
| PITFALL-D5: OAuth M2M not supported by decomposed path | Databricks | Databricks fix | MINOR |
| PITFALL-R1: Wrong method removed from Protocol | Dead code removal | Tech debt phase | CRITICAL |
| PITFALL-R2: Old plan docs re-introduce removed method | Dead code removal | All backend phases | MODERATE |
| PITFALL-R3: Property shadowing Pydantic field | Dead code removal | All backend phases | MODERATE |
| PITFALL-J1: `dbc` not in PATH — opaque failure | Justfile tooling | Foundry tooling phase | CRITICAL |
| PITFALL-J2: `dbc` version mismatch silent | Justfile tooling | Foundry tooling phase | MODERATE |
| PITFALL-J3: `which()` evaluates at parse time | Justfile tooling | Foundry tooling phase | MODERATE |
| PITFALL-J4: Driver installs to wrong path level | Justfile tooling | Foundry tooling phase | MODERATE |
| PITFALL-J5: Verify recipe checks existence not loadability | Justfile tooling | Foundry tooling phase | MINOR |

---

## Must-Resolve Before Implementation

These pitfalls must be addressed before writing any code in their respective areas:

1. **PITFALL-T1** — Confirm Teradata driver exists on docs.adbc-drivers.org before writing
   any `TeradataConfig` or `translate_teradata()` code. If absent, close the task.

2. **PITFALL-D1** + **PITFALL-D2** — Both the URL-encoding and the validation gate must be
   in the initial implementation of decomposed-field support. The validation gate should be
   added to `DatabricksConfig` even before the translator is updated — fixing the silent-empty-
   dict regression independently of the translator change.

3. **PITFALL-R1** — Grep `_adbc_driver_key` and `_adbc_entrypoint` in src/ before touching
   `_base_config.py`. Confirm which is live (`_adbc_entrypoint`) and which is already gone
   (`_adbc_driver_key`). Do not proceed if the grep is ambiguous.

4. **PITFALL-J1** + **PITFALL-J4** — The `command -v dbc` guard and `--level env` install
   flag must both be in the first version of the justfile recipe. These are not refinements
   to add later.

---

## Sources

### HIGH Confidence (verified against official docs, current source)

- `docs.adbc-drivers.org/drivers/index.html` — Foundry driver list (no Teradata, 8 drivers)
- `docs.adbc-drivers.org/drivers/databricks/index.html` — Databricks driver is URI-only
- `src/adbc_poolhouse/_base_config.py` (current source) — `_adbc_driver_key()` already removed
- `src/adbc_poolhouse/_databricks_translator.py` (current source) — URI-only, no decomposed fields
- `src/adbc_poolhouse/_mssql_translator.py` (current source) — dual-mode pattern reference
- `src/adbc_poolhouse/_drivers.py` (current source) — dispatch-table approach, `_adbc_entrypoint()` live
- `.planning/.continue-here.md` — confirms both dead code items removed in v0.1 cleanup
- deepwiki.com/columnar-tech/dbc/5.1-configuration-levels — `dbc` install paths per platform
- deepwiki.com/columnar-tech/adbc-quickstarts — MSSQL ADBC URI-only pattern

### MEDIUM Confidence (secondary sources, not verified against live install)

- `just` issue #2597 — `which()` parse-time evaluation documented by maintainer
- columnar.tech/blog/announcing-dbc-0.2.0 — `dbc` version history
- WebSearch results for Databricks ADBC URI format — consistent with official docs

### LOW Confidence (inferred from patterns, not directly verified)

- `dbc install --level env` flag behaviour — documented but not tested in this environment
- OAuth M2M URI construction from decomposed fields — inferred from URI format documentation;
  no authoritative confirmation that decomposed OAuth M2M fields are unsupported

---

*Generated: 2026-03-01*
*Scope: adbc-poolhouse v1.1.0 milestone pitfalls — four targeted risk areas*
*Supersedes: PITFALLS.md generated 2026-02-23 (greenfield implementation pitfalls)*
