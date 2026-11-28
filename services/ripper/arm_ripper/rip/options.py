"""How a DVD/BD rip is run, as the backend resolved it for the job."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RipOptions:
    """The per-rip choices that travel from the rip-start response down to makemkvcon.

    `per_title` rips each ticked title in its own invocation instead of one `mkv … all`. `end_on_completion` ends a
    makemkvcon run once it has reported the copy complete and its files are closed, instead of waiting for it to exit.
    `keep_3d_refs` are the `source_ref`s of the 3D titles whose MVC dependent view the rip keeps.
    `scan_min_length_seconds` is the minimum the disc's scan listed titles with: a per-title run passes it as
    `--minlength`, so MakeMKV numbers the titles as the scan did (None: the rip's own minimum).
    """

    per_title: bool = False
    end_on_completion: bool = False
    keep_3d_refs: frozenset[str] = field(default_factory=frozenset)
    scan_min_length_seconds: int | None = None
