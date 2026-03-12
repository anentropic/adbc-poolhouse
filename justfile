default:
    @just --list

# Set up the agent cli with GSD and skills based on agent name [claude|opencode]
setup-agent-cli agent="claude":
    @selected_agent="{{agent}}"; \
    selected_agent="${selected_agent#agent=}"; \
    case "${selected_agent}" in \
        claude) gsd_name="claude"; skills_name="claude-code" ;; \
        opencode) gsd_name="opencode"; skills_name="opencode" ;; \
        *) echo "Invalid agent '${selected_agent}'. Expected 'claude' or 'opencode'."; exit 1 ;; \
    esac; \
    npx get-shit-done-cc --"${gsd_name}" --local; \
    npx skills add abatilo/vimrc/plugins/abatilo-core/skills/diataxis-documentation -a "${skills_name}" -y; \
    npx skills add blader/humanizer -a "${skills_name}" -y

# Build the docs site (strict mode)
docs-build:
    uv run --group docs mkdocs build --strict

# Serve the docs dev server (default port 8000)
docs-serve port="8000":
    uv run --group docs mkdocs serve --dev-addr 127.0.0.1:{{port}} --livereload

# Install the dbc CLI for Foundry driver management (only if not already on PATH).
# Uses 'command -v' — the POSIX standard; 'which' is not portable in just's shell context.
install-dbc:
    command -v dbc || curl -LsSf https://dbc.columnar.tech/install.sh | sh

# Install all 12 ADBC drivers (PyPI + Foundry) for semi-integration tests.
# PyPI drivers: duckdb, snowflake, bigquery, postgresql, flightsql, sqlite
# Foundry drivers: databricks, redshift, trino, mssql, mysql, clickhouse
install-all-drivers: install-dbc
    uv sync --dev
    dbc install databricks
    dbc install redshift
    dbc install trino
    dbc install mssql
    dbc install mysql
    dbc install --pre clickhouse
