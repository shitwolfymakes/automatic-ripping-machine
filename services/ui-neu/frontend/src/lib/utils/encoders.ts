// Encoder id -> label, for components that render a preset's saved encoder
// id without fetching the live GET /api/encoders catalog (e.g. a preset list
// row). The transcode preset form itself gets its options from
// $lib/api/encoders's fetchEncoders instead, since it also needs the
// per-deployment availability/reason that this static map does not carry.
// Mirrors the arm_common.encoders catalog; the backend validates every
// choice and its tool scope.

export const PRESET_ENCODER_ID = 'preset';

const LABELS: Readonly<Record<string, string>> = {
	cpu_h264: 'CPU H.264',
	cpu_h265: 'CPU H.265',
	cpu_av1: 'CPU AV1',
	any_h264: 'Any GPU H.264',
	any_h265: 'Any GPU H.265',
	any_av1: 'Any GPU AV1',
	qsv_h264: 'Intel QSV H.264',
	qsv_h265: 'Intel QSV H.265',
	qsv_av1: 'Intel QSV AV1',
	nvenc_h264: 'NVIDIA NVENC H.264',
	nvenc_h265: 'NVIDIA NVENC H.265',
	nvenc_av1: 'NVIDIA NVENC AV1',
	vaapi_h264: 'AMD VAAPI H.264',
	vaapi_h265: 'AMD VAAPI H.265',
	vaapi_av1: 'AMD VAAPI AV1'
};

/** Summary label for a preset's encoder: '' for the tool's own encoder (a
 * passthrough or abcde preset has nothing to add), the catalog label
 * otherwise, and the raw id for anything the catalog does not list. */
export function encoderSummary(id: string | null | undefined): string {
	if (!id || id === PRESET_ENCODER_ID) return '';
	return LABELS[id] ?? id;
}
