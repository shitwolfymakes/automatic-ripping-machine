// Transcode preset encoder ids and labels. Mirrors the arm_common.encoders
// catalog; the backend validates every choice and its tool scope.

export const PRESET_ENCODER_ID = 'preset';

export const ENCODER_OPTIONS: readonly { id: string; label: string }[] = [
	{ id: PRESET_ENCODER_ID, label: "HandBrake preset's own encoder" },
	{ id: 'cpu_h264', label: 'CPU H.264' },
	{ id: 'cpu_h265', label: 'CPU H.265' },
	{ id: 'cpu_av1', label: 'CPU AV1' },
	{ id: 'any_h264', label: 'Any GPU H.264' },
	{ id: 'any_h265', label: 'Any GPU H.265' },
	{ id: 'any_av1', label: 'Any GPU AV1' },
	{ id: 'qsv_h264', label: 'Intel QSV H.264' },
	{ id: 'qsv_h265', label: 'Intel QSV H.265' },
	{ id: 'qsv_av1', label: 'Intel QSV AV1' },
	{ id: 'nvenc_h264', label: 'NVIDIA NVENC H.264' },
	{ id: 'nvenc_h265', label: 'NVIDIA NVENC H.265' },
	{ id: 'nvenc_av1', label: 'NVIDIA NVENC AV1' },
	{ id: 'vaapi_h264', label: 'AMD VAAPI H.264' },
	{ id: 'vaapi_h265', label: 'AMD VAAPI H.265' },
	{ id: 'vaapi_av1', label: 'AMD VAAPI AV1' }
];

/** Summary label for a preset's encoder: '' for the tool's own encoder (a
 * passthrough or abcde preset has nothing to add), the catalog label
 * otherwise, and the raw id for anything the catalog does not list. */
export function encoderSummary(id: string | null | undefined): string {
	if (!id || id === PRESET_ENCODER_ID) return '';
	return ENCODER_OPTIONS.find((o) => o.id === id)?.label ?? id;
}
