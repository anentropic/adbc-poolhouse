# adbc-poolhouse

Connection pooling for ADBC drivers from typed warehouse configs

## Installation

```bash
pip install adbc-poolhouse
```

## Development

### Quality Gates

Before committing, all code must pass:

```bash
prek run --all-files  # Runs typecheck, lint, format, test
```

Or run individually:
```bash
uv run basedpyright  # Type checking (strict mode)
uv run ruff check    # Linting
uv run ruff format --check  # Formatting
uv run pytest        # Tests
```

### Setup

```bash
# Install dependencies
uv sync --dev

# Install git hooks
prek install
```

## License

MIT
