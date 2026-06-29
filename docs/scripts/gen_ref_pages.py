"""Generate API reference pages for all modules."""

from pathlib import Path

import mkdocs_gen_files

# Explicit reference blocks for the experimental async surface.
#
# AsyncPool/AsyncConnection/AsyncCursor live under the private `_async` package
# and are intentionally NOT promoted to `__all__` or the PEP-562 lazy exports
# (D-28-02): users never construct them, they are returned objects, and the
# surface is experimental (D-28-01). The auto-generation loop below skips every
# `_`-prefixed module part, so these classes never get their own page. We append
# explicit mkdocstrings blocks at their real `_async` module paths to the
# top-level package page instead (DOCS-02).
#
# Each block carries a per-block `filters: ["!^__"]` override. The global
# mkdocs.yml filter is `["!^_"]`, which would strip the single-underscore
# `_async._*` path; per-block `options.filters` REPLACES (does not merge with)
# the global filter, so `["!^__"]` admits the `_async._*` path while still
# hiding dunder members.
_ASYNC_REFERENCE_BLOCK = """
## Async API (experimental)

You never construct these classes yourself. They are returned by the async
entry-point functions above (`create_async_pool` returns an `AsyncPool`, whose
`connect` yields an `AsyncConnection`, whose `cursor` yields an `AsyncCursor`).
They are documented here at their real module paths because the async surface is
experimental and is not part of the constructible public API.

::: adbc_poolhouse._async._pool.AsyncPool
    options:
      show_root_heading: true
      members_order: source
      filters: ["!^__"]

::: adbc_poolhouse._async._connection.AsyncConnection
    options:
      show_root_heading: true
      members_order: source
      filters: ["!^__"]

::: adbc_poolhouse._async._cursor.AsyncCursor
    options:
      show_root_heading: true
      members_order: source
      filters: ["!^__"]
"""


def main():
    src = Path("src")
    nav = mkdocs_gen_files.Nav()

    for path in sorted(src.rglob("*.py")):
        module_path = path.relative_to(src).with_suffix("")
        doc_path = path.relative_to(src).with_suffix(".md")
        full_doc_path = Path("reference", doc_path)

        parts = tuple(module_path.parts)

        # Include the top-level package __init__ as the main API reference page.
        # All other __init__, __main__, and conftest files are skipped.
        if parts[-1] in ("__main__", "conftest"):
            continue
        if parts[-1] == "__init__":
            if len(parts) == 2:  # e.g. ("adbc_poolhouse", "__init__")
                # Generate a reference page for the top-level package
                pkg_parts = parts[:-1]  # ("adbc_poolhouse",)
                pkg_doc_path = Path(*pkg_parts).with_suffix(".md")
                full_pkg_doc_path = Path("reference", pkg_doc_path)
                nav[pkg_parts] = pkg_doc_path.as_posix()
                with mkdocs_gen_files.open(full_pkg_doc_path, "w") as fd:
                    ident = ".".join(pkg_parts)
                    fd.write(f"# `{ident}`\n\n::: {ident}\n")
                    fd.write(_ASYNC_REFERENCE_BLOCK)
                mkdocs_gen_files.set_edit_path(full_pkg_doc_path, path)
            continue

        if any(part.startswith("_") for part in parts):
            continue

        nav[parts] = doc_path.as_posix()

        with mkdocs_gen_files.open(full_doc_path, "w") as fd:
            ident = ".".join(parts)
            fd.write(f"# `{ident}`\n\n::: {ident}\n")

        mkdocs_gen_files.set_edit_path(full_doc_path, path)

    with mkdocs_gen_files.open("reference/SUMMARY.md", "w") as nav_file:
        nav_file.writelines(nav.build_literate_nav())


main()
