# Build the docs site (strict mode)
build:
    uv run --group docs mkdocs build --strict

# Serve the docs dev server (default port 8000)
serve port="8000":
    uv run --group docs mkdocs serve --dev-addr 127.0.0.1:{{port}} --livereload
