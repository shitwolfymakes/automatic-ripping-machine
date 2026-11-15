"""ARM's overlay on the libhb schema dump. Data only: nothing here is computed from the dump.

libhb reports every key's type and default and the encoder, audio and filter lists. It does not say
which GUI tab or group a key belongs to, what to call it, which list constrains it, or the accepted
strings of the keys libhb parses with ``strcasecmp`` chains. Those live here, read from HandBrake
1.11.1's ``libhb/preset.c``. A template key with no row is still a setting (typed from its default,
shown under "Other"); a row for a key the dump no longer has is ignored.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from arm_common.handbrake_schema.types import QualityLimits, ValueSource

# Keys ARM sets itself; they are never stored as user settings.
ARM_OWNED_KEYS: frozenset[str] = frozenset(
    {
        "PresetName",
        "PresetDescription",
        "Type",
        "Default",
        "Folder",
        "FolderOpen",
        "ChildrenArray",
        "PresetDisabled",
        "VideoEncoder",
        "FileFormat",
        "VideoHWDecode",
    }
)

# Keys whose meaning depends on the encoder: libhb drops them when --encoder overrides the preset.
ENCODER_SPECIFIC_KEYS: frozenset[str] = frozenset(
    {
        "VideoPreset",
        "VideoTune",
        "VideoProfile",
        "VideoLevel",
        "VideoOptionExtra",
        "VideoQualitySlider",
        "VideoMultiPass",
        "VideoTurboMultiPass",
        "x264UseAdvancedOptions",
        "x264Option",
    }
)

# The HandBrakeCLI flag that re-applies each encoder-specific string key after --encoder.
FLAG_KEYS: dict[str, str] = {
    "VideoPreset": "--encoder-preset",
    "VideoTune": "--encoder-tune",
    "VideoProfile": "--encoder-profile",
    "VideoLevel": "--encoder-level",
    "VideoOptionExtra": "--encopts",
}

# libhb returns no quality limits for QSV without an Intel adapter; this is the ICQ range from source.
QSV_QUALITY_FALLBACK = QualityLimits(1, 51, 1, "ICQ")

# Families libhb applies turbo first pass to.
TURBO_FAMILIES: frozenset[str] = frozenset({"x264", "x265"})

# VideoQualityType codes every family accepts: 1 average bitrate, 2 constant quality.
DEFAULT_RATE_CONTROLS: frozenset[int] = frozenset({1, 2})

# Accepted values of the keys libhb parses by hand (libhb/preset.c, 1.11.1). Integer enums are codes.
STATIC_ENUMS: dict[str, tuple[Any, ...]] = {
    "AudioAutomaticNamingBehavior": ("none", "unnamed", "all"),
    "AudioTrackSelectionBehavior": ("none", "first", "all"),
    "SubtitleTrackSelectionBehavior": ("none", "first", "all"),
    "SubtitleBurnBehavior": ("none", "foreign", "first", "foreign_first"),
    "PicturePAR": ("off", "auto", "strict", "custom", "loose"),
    "PicturePadMode": ("none", "custom", "fill", "letterbox", "pillarbox"),
    "PictureCropMode": (0, 1, 2, 3),  # automatic, loose, none, custom
    "PictureDeinterlaceFilter": ("off", "decomb", "deinterlace", "bwdif"),
    "PictureDenoiseFilter": ("off", "hqdn3d", "nlmeans"),
    "PictureSharpenFilter": ("off", "lapsharp", "unsharp"),
    "VideoColorRange": ("limited", "full", "auto"),
    "VideoFramerateMode": ("vfr", "cfr", "pfr"),
    "VideoPasshtruHDRDynamicMetadata": ("all", "off", "hdr10plus", "dolbyvision"),
    "VideoQualityType": (1, 2),  # average bitrate, constant quality
    "VideoScaler": ("swscale", "zscale"),
    "PictureModulus": (2, 4, 8, 16),
    "VideoColorMatrixCodeOverride": (0, 1, 2, 3, 4),  # codes libhb/preset.c maps to a primaries/transfer/matrix set
    "PicturePadColor": ("black", "white", "gray", "red", "green", "blue"),  # a few of libhb's X11 colour names
}

# Enum keys whose list only suggests values: the validator also accepts any other string (a further colour name
# or a hex code), because libhb resolves those itself.
OPEN_ENUMS: frozenset[str] = frozenset({"PicturePadColor"})

# Display labels for enum values, keyed by str(value). Values without a label fall back to the raw value in the UI.
OPTION_LABELS: dict[str, dict[str, str]] = {
    "VideoQualityType": {"1": "Average bitrate", "2": "Constant quality"},
    "VideoFramerate": {"auto": "Same as source"},
    "VideoFramerateMode": {"cfr": "Constant", "vfr": "Variable", "pfr": "Peak"},
    "VideoColorRange": {"auto": "Same as source", "limited": "Limited", "full": "Full"},
    "VideoPasshtruHDRDynamicMetadata": {
        "all": "Pass through all",
        "off": "Off",
        "hdr10plus": "HDR10+",
        "dolbyvision": "Dolby Vision",
    },
    "PicturePadMode": {
        "none": "None",
        "custom": "Custom",
        "fill": "Fill",
        "letterbox": "Letterbox",
        "pillarbox": "Pillarbox",
    },
    "VideoScaler": {"swscale": "Software scaler (swscale)", "zscale": "zimg (zscale)"},
    "VideoColorMatrixCodeOverride": {
        "0": "No override",
        "1": "BT.601 NTSC (SD)",
        "2": "BT.601 PAL (SD)",
        "3": "BT.709 (HD)",
        "4": "BT.2020 (UHD)",
    },
    "PicturePadColor": {
        "black": "Black",
        "white": "White",
        "gray": "Gray",
        "red": "Red",
        "green": "Green",
        "blue": "Blue",
    },
    "PictureCropMode": {"0": "Automatic", "1": "Loose", "2": "None", "3": "Custom"},
    "SubtitleBurnBehavior": {
        "none": "None",
        "foreign": "Foreign audio scan",
        "first": "First track",
        "foreign_first": "Foreign audio scan, then first track",
    },
}

# A selector value that names a filter differently from the dump's filter name.
SELECTOR_FILTER_ALIASES: dict[str, str] = {"deinterlace": "yadif"}

# Values a key accepts beyond its source list ("same as source" and "unset" sentinels).
SOURCE_EXTRAS: dict[str, tuple[Any, ...]] = {
    "VideoFramerate": ("auto",),
    "AudioSamplerate": ("auto",),
    "AudioBitrate": (-1,),
}

# The Picture* keys that belong on the Filters tab rather than Dimensions.
FILTER_TAB_KEYS: frozenset[str] = frozenset(
    {
        "PictureChromaSmoothCustom",
        "PictureChromaSmoothPreset",
        "PictureChromaSmoothTune",
        "PictureColorspaceCustom",
        "PictureColorspacePreset",
        "PictureCombDetectCustom",
        "PictureCombDetectPreset",
        "PictureDeblockCustom",
        "PictureDeblockPreset",
        "PictureDeblockTune",
        "PictureDeinterlaceCustom",
        "PictureDeinterlaceFilter",
        "PictureDeinterlacePreset",
        "PictureDenoiseCustom",
        "PictureDenoiseFilter",
        "PictureDenoisePreset",
        "PictureDenoiseTune",
        "PictureDetelecine",
        "PictureDetelecineCustom",
        "PictureSharpenCustom",
        "PictureSharpenFilter",
        "PictureSharpenPreset",
        "PictureSharpenTune",
    }
)


@dataclass(frozen=True)
class KeyOverlay:
    tab: str
    group: str
    label: str
    source: ValueSource | None = None
    limits: tuple[float, float] | None = None


def _enum(key: str) -> ValueSource:
    return ValueSource("static", key)


def _list(name: str) -> ValueSource:
    return ValueSource("schema_list", name)


def _presets(ref: str) -> ValueSource:
    return ValueSource("filter_presets", ref)


def _tunes(ref: str) -> ValueSource:
    return ValueSource("filter_tunes", ref)


Item = tuple[Any, ...]  # (key, label) | (key, label, source) | (key, label, source, limits)


def _rows(tab: str, group: str, *items: Item) -> dict[str, KeyOverlay]:
    return {key: KeyOverlay(tab, group, label, *rest) for key, label, *rest in items}


KEY_OVERLAY: dict[str, KeyOverlay] = {
    **_rows(
        "summary",
        "Container",
        ("AlignAVStart", "Align audio and video start"),
        ("InlineParameterSets", "Inline parameter sets"),
        ("MetadataPassthru", "Pass through metadata"),
        ("Mp4iPodCompatible", "iPod 5G compatible"),
        ("Optimize", "Web optimized"),
    ),
    **_rows("chapters", "Chapters", ("ChapterMarkers", "Create chapter markers")),
    **_rows(
        "dimensions",
        "Size",
        ("PictureWidth", "Maximum width"),
        ("PictureHeight", "Maximum height"),
        ("PictureForceWidth", "Force width"),
        ("PictureForceHeight", "Force height"),
        ("PictureUseMaximumSize", "Use the maximum size"),
        ("PictureAllowUpscaling", "Allow upscaling"),
        ("PictureKeepRatio", "Keep aspect ratio"),
        ("PictureModulus", "Storage alignment (modulus)", _enum("PictureModulus")),
        ("VideoScaler", "Scaler", _enum("VideoScaler")),
    ),
    **_rows(
        "dimensions",
        "Cropping",
        ("PictureCropMode", "Crop mode", _enum("PictureCropMode")),
        ("PictureAutoCrop", "Crop automatically"),
        ("PictureTopCrop", "Top crop"),
        ("PictureBottomCrop", "Bottom crop"),
        ("PictureLeftCrop", "Left crop"),
        ("PictureRightCrop", "Right crop"),
    ),
    **_rows(
        "dimensions",
        "Pixel aspect",
        ("PicturePAR", "Pixel aspect mode", _enum("PicturePAR")),
        ("PictureItuPAR", "Use ITU pixel aspect"),
        ("PicturePARWidth", "Pixel aspect width"),
        ("PicturePARHeight", "Pixel aspect height"),
        ("PictureDARWidth", "Display aspect width"),
    ),
    **_rows(
        "dimensions",
        "Padding",
        ("PicturePadMode", "Padding mode", _enum("PicturePadMode")),
        ("PicturePadColor", "Padding color", _enum("PicturePadColor")),
        ("PicturePadTop", "Top padding"),
        ("PicturePadBottom", "Bottom padding"),
        ("PicturePadLeft", "Left padding"),
        ("PicturePadRight", "Right padding"),
    ),
    **_rows("dimensions", "Orientation", ("PictureRotate", "Rotate and flip")),
    **_rows(
        "filters",
        "General",
        ("UsesPictureFilters", "Use picture filters"),
        ("VideoGrayScale", "Grayscale"),
    ),
    **_rows(
        "filters",
        "Detelecine",
        ("PictureDetelecine", "Detelecine preset", _presets("detelecine")),
        ("PictureDetelecineCustom", "Detelecine custom settings"),
    ),
    **_rows(
        "filters",
        "Interlace detection",
        ("PictureCombDetectPreset", "Comb detection preset", _presets("comb_detect")),
        ("PictureCombDetectCustom", "Comb detection custom settings"),
    ),
    **_rows(
        "filters",
        "Deinterlace",
        ("PictureDeinterlaceFilter", "Deinterlace filter", _enum("PictureDeinterlaceFilter")),
        ("PictureDeinterlacePreset", "Deinterlace preset", _presets("PictureDeinterlaceFilter")),
        ("PictureDeinterlaceCustom", "Deinterlace custom settings"),
    ),
    **_rows(
        "filters",
        "Denoise",
        ("PictureDenoiseFilter", "Denoise filter", _enum("PictureDenoiseFilter")),
        ("PictureDenoisePreset", "Denoise preset", _presets("PictureDenoiseFilter")),
        ("PictureDenoiseTune", "Denoise tune", _tunes("PictureDenoiseFilter")),
        ("PictureDenoiseCustom", "Denoise custom settings"),
    ),
    **_rows(
        "filters",
        "Chroma smooth",
        ("PictureChromaSmoothPreset", "Chroma smooth preset", _presets("chroma_smooth")),
        ("PictureChromaSmoothTune", "Chroma smooth tune", _tunes("chroma_smooth")),
        ("PictureChromaSmoothCustom", "Chroma smooth custom settings"),
    ),
    **_rows(
        "filters",
        "Sharpen",
        ("PictureSharpenFilter", "Sharpen filter", _enum("PictureSharpenFilter")),
        ("PictureSharpenPreset", "Sharpen preset", _presets("PictureSharpenFilter")),
        ("PictureSharpenTune", "Sharpen tune", _tunes("PictureSharpenFilter")),
        ("PictureSharpenCustom", "Sharpen custom settings"),
    ),
    **_rows(
        "filters",
        "Deblock",
        ("PictureDeblockPreset", "Deblock preset", _presets("deblock")),
        ("PictureDeblockTune", "Deblock tune", _tunes("deblock")),
        ("PictureDeblockCustom", "Deblock custom settings"),
    ),
    **_rows(
        "filters",
        "Colorspace",
        ("PictureColorspacePreset", "Colorspace preset", _presets("colorspace")),
        ("PictureColorspaceCustom", "Colorspace custom settings"),
    ),
    **_rows(
        "video",
        "Rate control",
        ("VideoQualityType", "Rate control mode", _enum("VideoQualityType")),
        ("VideoQualitySlider", "Constant quality"),
        ("VideoAvgBitrate", "Average bitrate (kbit/s)"),
        ("VideoMultiPass", "Multi-pass encoding"),
        ("VideoTurboMultiPass", "Turbo first pass"),
    ),
    # Preset, tune, profile and level lists depend on the encoder, so they carry no source here.
    **_rows(
        "video",
        "Encoder",
        ("VideoPreset", "Encoder preset"),
        ("VideoTune", "Encoder tune"),
        ("VideoProfile", "Encoder profile"),
        ("VideoLevel", "Encoder level"),
        ("VideoOptionExtra", "Additional encoder options"),
        ("x264UseAdvancedOptions", "Use x264 advanced options"),
        ("x264Option", "x264 advanced options"),
    ),
    **_rows(
        "video",
        "Framerate",
        ("VideoFramerate", "Framerate", _list("video_framerates")),
        ("VideoFramerateMode", "Framerate mode", _enum("VideoFramerateMode")),
    ),
    **_rows(
        "video",
        "Color",
        ("VideoColorRange", "Color range", _enum("VideoColorRange")),
        ("VideoColorMatrixCodeOverride", "Color matrix override", _enum("VideoColorMatrixCodeOverride")),
        (
            "VideoPasshtruHDRDynamicMetadata",
            "HDR dynamic metadata",
            _enum("VideoPasshtruHDRDynamicMetadata"),
        ),
    ),
    **_rows(
        "audio",
        "Track selection",
        ("AudioLanguageList", "Languages"),
        ("AudioTrackSelectionBehavior", "Track selection", _enum("AudioTrackSelectionBehavior")),
    ),
    **_rows(
        "audio",
        "Passthru",
        ("AudioCopyMask", "Allowed passthru formats", _list("audio_encoders")),
        ("AudioEncoderFallback", "Fallback encoder", _list("audio_encoders")),
        ("AudioSecondaryEncoderMode", "Allow a secondary encoder"),
    ),
    **_rows(
        "audio",
        "Names",
        ("AudioTrackNamePassthru", "Pass through track names"),
        ("AudioAutomaticNamingBehavior", "Automatic track names", _enum("AudioAutomaticNamingBehavior")),
    ),
    **_rows("audio", "Tracks", ("AudioList", "Audio tracks")),
    # The keys of one AudioList item.
    **_rows(
        "audio",
        "Track settings",
        ("AudioEncoder", "Encoder", _list("audio_encoders")),
        ("AudioMixdown", "Mixdown", ValueSource("audio_mixdowns", "AudioEncoder")),
        ("AudioSamplerate", "Sample rate", _list("audio_samplerates")),
        ("AudioBitrate", "Bitrate (kbit/s)", _list("audio_bitrates")),
        ("AudioTrackQualityEnable", "Use quality instead of bitrate"),
        ("AudioTrackQuality", "Quality"),
        ("AudioCompressionLevel", "Compression level"),
        ("AudioDitherMethod", "Dither", _list("audio_dithers")),
        ("AudioNormalizeMixLevel", "Normalize mix level"),
        ("AudioTrackDRCSlider", "Dynamic range compression", None, (0, 4)),
        ("AudioTrackGainSlider", "Gain (dB)", None, (-20, 20)),
    ),
    **_rows(
        "subtitles",
        "Track selection",
        ("SubtitleLanguageList", "Languages"),
        ("SubtitleTrackSelectionBehavior", "Track selection", _enum("SubtitleTrackSelectionBehavior")),
        ("SubtitleAddForeignAudioSearch", "Add a foreign audio search track"),
        ("SubtitleAddForeignAudioSubtitle", "Add a foreign audio subtitle track"),
        ("SubtitleAddCC", "Add closed captions"),
        ("SubtitleTrackNamePassthru", "Pass through track names"),
    ),
    **_rows(
        "subtitles",
        "Burn in",
        ("SubtitleBurnBehavior", "Burn in behavior", _enum("SubtitleBurnBehavior")),
        ("SubtitleBurnDVDSub", "Burn in DVD subtitles"),
        ("SubtitleBurnBDSub", "Burn in Blu-ray subtitles"),
    ),
}
