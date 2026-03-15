---
phase: 20
title: Plugin Author Documentation
status: not-started
depends_on: [19]
---

## Goal

Document how 3rd party libraries implement custom ADBC backends for
adbc-poolhouse. After registration removal, the story is simple: define a
config class with the required methods, pass it to `create_pool()`.

## Key Deliverables

- "Custom Backends" guide in docs/
- Minimal example config class
- Protocol reference (required methods: to_adbc_kwargs, _driver_path, _adbc_entrypoint, etc.)
- `mkdocs build --strict` passes
