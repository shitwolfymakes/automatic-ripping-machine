import logging
from collections.abc import Awaitable, Callable
from pathlib import Path

from arm_common import DiscType
from arm_common.schemas import TrackView

from arm_ripper.rip.abcde_rip import rip_cd
from arm_ripper.rip.data_rip import rip_data
from arm_ripper.rip.makemkv_rip import RipResult, rip_title

logger = logging.getLogger("arm_ripper.rip.dispatcher")

OnTrackStart = Callable[[TrackView], Awaitable[None]]
OnTrackDone = Callable[[TrackView, RipResult], Awaitable[None]]
OnTrackProgress = Callable[[TrackView, float], Awaitable[None]]


async def rip_all(
    disc_type: DiscType,
    device_path: str,
    tracks: list[TrackView],
    output_dir: Path,
    on_track_start: OnTrackStart,
    on_track_done: OnTrackDone,
    on_track_progress: OnTrackProgress | None = None,
) -> None:
    """Rip every track in `tracks` and invoke the lifecycle callbacks.

    Per disc_type:
    - DVD / BD: iterate tracks; one makemkvcon invocation per title.
    - CD: mark all tracks IN_PROGRESS, run abcde once for the whole disc,
      then emit DONE/FAILED per track from the bulk result.
    - DATA: a single dd dump assigned to the first (only) track.
    """
    if disc_type in (DiscType.DVD, DiscType.BLURAY):
        for track in tracks:
            await on_track_start(track)

            async def _on_progress(fraction: float, t: TrackView = track) -> None:
                if on_track_progress is not None:
                    await on_track_progress(t, fraction)

            try:
                title_index = int(track.source_ref)
            except ValueError:
                await on_track_done(
                    track,
                    RipResult(ok=False, error=f"invalid source_ref: {track.source_ref!r}"),
                )
                continue

            result = await rip_title(
                device_path=device_path,
                title_index=title_index,
                output_dir=output_dir,
                expected_duration_seconds=track.duration_seconds,
                on_progress=_on_progress,
            )
            await on_track_done(track, result)
        return

    if disc_type == DiscType.CD:
        for track in tracks:
            await on_track_start(track)
        results = await rip_cd(
            device_path=device_path,
            output_dir=output_dir,
            track_indexes=[t.index for t in tracks],
        )
        for track in tracks:
            result = results.get(
                track.index,
                RipResult(ok=False, error=f"abcde produced no entry for track {track.index}"),
            )
            await on_track_done(track, result)
        return

    if disc_type == DiscType.DATA:
        if not tracks:
            return
        first = tracks[0]
        await on_track_start(first)
        result = await rip_data(device_path=device_path, output_dir=output_dir)
        await on_track_done(first, result)
        return

    for track in tracks:
        await on_track_done(
            track,
            RipResult(ok=False, error=f"no rip path for disc_type={disc_type.value}"),
        )
