"""ExtensionData lookup, the container MPLS and CLPI files share for later additions.

Layout: length u32, data_block_start u32, reserved u8[3], entry count u8, then
12-byte entries (type u16, version u16, start u32 from the ExtensionData's own
start, length u32). Pure: no disc I/O.
"""

from __future__ import annotations

import struct

_ENTRIES_OFFSET = 12
_ENTRY_SIZE = 12


def extension_block(data: bytes, ext_start: int, kind: tuple[int, int]) -> int | None:
    """Absolute offset of the (type, version) block, or None when `ext_start` is 0 or the block is absent.

    Raises struct.error when the entry table runs past the data.
    """
    if not ext_start:
        return None
    count: int = data[ext_start + 11]
    for i in range(count):
        ext_type, version, start, _length = struct.unpack_from(
            ">HHII", data, ext_start + _ENTRIES_OFFSET + i * _ENTRY_SIZE
        )
        if (ext_type, version) == kind:
            return int(ext_start + start)
    return None
