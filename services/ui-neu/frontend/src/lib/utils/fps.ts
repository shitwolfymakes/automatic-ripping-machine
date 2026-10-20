/**
 * Encoder frame rate as the transcode card and the job page show it:
 * "45.7 fps (avg 23.5)", or "45.7 fps" when the engine has no running
 * average (ffmpeg). Null when no rate has been reported yet.
 */
export function formatFps(fps: number | null | undefined, avgFps?: number | null): string | null {
	if (fps == null) return null;
	const live = `${fps.toFixed(1)} fps`;
	return avgFps == null ? live : `${live} (avg ${avgFps.toFixed(1)})`;
}
