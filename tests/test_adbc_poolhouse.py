"""Basic tests for adbc_poolhouse."""

import adbc_poolhouse


def test_import():
    assert hasattr(adbc_poolhouse, "__all__")
