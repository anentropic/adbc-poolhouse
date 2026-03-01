# Build the docs site (strict mode)
build:
    uv run --group docs mkdocs build --strict

# Serve the docs dev server (default port 8000)
serve port="8000":
    uv run --group docs mkdocs serve --dev-addr 127.0.0.1:{{port}} --livereload

# Install the dbc CLI for Foundry driver management (only if not already on PATH).
# Uses 'command -v' — the POSIX standard; 'which' is not portable in just's shell context.
install-dbc:
    command -v dbc || curl -LsSf https://dbc.columnar.tech/install.sh | sh

# Install MySQL and ClickHouse Foundry ADBC drivers into the active virtualenv.
# dbc detects VIRTUAL_ENV automatically — no --level flag required.
# Two separate calls: dbc install with multiple args is not confirmed by official docs.
install-foundry-drivers:
    dbc install mysql
    dbc install clickhouse
