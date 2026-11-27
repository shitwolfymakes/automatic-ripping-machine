"""ExtensionData lookup shared by the MPLS and CLPI readers."""

from __future__ import annotations

import struct

import pytest
from bd_builders import extension_data

from arm_ripper.scan.bd_extension_data import extension_block


def test_finds_the_block_of_a_type_and_version() -> None:
    data = b"\xaa" * 5 + extension_data({(2, 1): b"first", (2, 2): b"second!"})
    offset = extension_block(data, 5, (2, 2))
    assert offset is not None
    assert data[offset : offset + 7] == b"second!"


def test_missing_block_is_none() -> None:
    data = extension_data({(2, 1): b"first"})
    assert extension_block(data, 0, (2, 2)) is None


def test_no_extension_is_none() -> None:
    assert extension_block(b"MPLS0200", 0, (2, 2)) is None


def test_truncated_entry_table_raises() -> None:
    data = b"\x00" * 5 + extension_data({(2, 1): b"first", (2, 2): b"second"})
    with pytest.raises(struct.error):
        extension_block(data[:25], 5, (2, 2))
