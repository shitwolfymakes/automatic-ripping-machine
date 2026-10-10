# Intel QSV transcode on Gen12+ iGPUs needs the oneVPL GPU runtime

## Symptom

On a Gen12+ Intel iGPU (Alder Lake / N-series; e.g. the N97, iHD driver 23.x)
every QSV transcode fails immediately. HandBrake selects the QSV encoder, reaches
encoder init, then dies:

```
[…] encavcodecInit: H.264 (Intel Quick Sync Video)
[QSV @ …] Error setting child device handle: -17
ERROR: hwaccel: failed to create hwdevice
ERROR: Failure to initialise thread 'FFMPEG encoder (libavcodec)'
[…] libhb: work result = 3
Encode failed (error 3).
```

The task ends `rc=3`. Today this is caught before it ever reaches a real job:
the backend's per-device probe test-encodes with QSV before advertising the
row as eligible, so a Gen12+ device stuck this way simply verifies nothing
and an `any_h265`-style preset runs on CPU from the start, rather than a
job failing mid-transcode and falling back. On small fanless Intel boxes a
CPU software encode can still peg all cores for hours, so the fix below is
worth applying either way.

## Root cause

The transcode image shipped the oneVPL **dispatcher** (`libvpl2`) and the
**legacy** Intel Media SDK GPU runtime (`libmfxhw64.so`), but **not** the modern
oneVPL **GPU runtime** (`libmfx-gen`). On Gen12+ silicon the legacy Media SDK is
deprecated/unsupported, so oneVPL falls back to it and fails with the `-17`
child-device-handle error.

It is **not** a device or permission problem: the render node is passed into the
container, the iHD driver loads, and `vainfo` reports `VAProfileH264High :
VAEntrypointEncSlice` (VA-API h264 encode is available). The sole missing piece
is the GPU-side oneVPL runtime package.

## Fix

Install `libmfx-gen1.2` (Intel oneVPL GPU Runtime) alongside `libvpl2` in the
transcode image (`services/transcode/Dockerfile`). With it present, oneVPL
dispatches to the modern runtime and QSV hardware encode succeeds.

## Verification

On an Intel N97, after adding the package, `HandBrakeCLI … -e qsv_h264` produces
`encavcodecInit: H.264 (Intel Quick Sync Video)` → `libhb: work result = 0` →
`Encode done!` with output written, and a full rip→transcode→completed run lands
the finished `.mkv` in the media root. No `-17`, no rc=3, no CPU fallback.
