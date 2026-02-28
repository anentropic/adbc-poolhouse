# Build the docs site (strict mode)
build:
    uv run mkdocs build --strict

# Serve the docs dev server (default port 8000)
serve port="8000":
    uv run mkdocs serve --dev-addr 0.0.0.0:{{port}}
