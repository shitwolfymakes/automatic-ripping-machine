"""Disc-wide rip progress across the one-invocation-per-title rips of a disc.

Each makemkvcon run reports only its own title's fraction. The UI shows one bar per disc and restarts its ETA when the
percentage drops, so the fractions are weighed by title size into one disc-wide figure that never goes back.
"""

from collections.abc import Collection, Mapping


def disc_progress(done_bytes: int, current_bytes: int, fraction: float, total_bytes: int) -> float:
    """The disc-wide fraction: the bytes of the titles done plus `fraction` of the current title's, over the total."""
    if total_bytes <= 0:
        return 0.0
    covered = done_bytes + current_bytes * min(max(fraction, 0.0), 1.0)
    return min(covered / total_bytes, 1.0)


class DiscProgress:
    """Disc-wide progress for the titles of one rip, weighed by expected size.

    Titles with no expected size weigh the same as each other, as do all of them when any size is missing. The
    figure only ever rises, so a title retried from its start does not pull it back.
    """

    def __init__(self, expected_bytes: Mapping[int, int | None], settled: Collection[int]) -> None:
        sized = all(size is not None for size in expected_bytes.values())
        self._weights = {idx: (size or 0) if sized else 1 for idx, size in expected_bytes.items()}
        self._total = sum(self._weights.values())
        self._settled: set[int] = {idx for idx in settled if idx in self._weights}
        self._highest = 0.0

    def settle(self, title: int) -> None:
        """Count a title as over, ripped or not, so the next one starts from its share."""
        self._settled.add(title)

    def fraction(self, title: int, title_fraction: float) -> float:
        """The disc-wide fraction with `title` at `title_fraction` of its own."""
        done = sum(self._weights[idx] for idx in self._settled)
        current = disc_progress(done, self._weights[title], title_fraction, self._total)
        self._highest = max(self._highest, current)
        return self._highest
