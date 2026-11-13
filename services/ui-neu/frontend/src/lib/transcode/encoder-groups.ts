// The transcode preset form's encoder select: the catalog grouped into
// optgroups, in a fixed order, each with its heading.
import type { EncoderAvailabilityView } from '$lib/types/api.gen';

// Encoder optgroup order and headings; a group is only rendered when the
// catalog response has an entry for it.
const GROUP_ORDER: EncoderAvailabilityView['group'][] = ['preset', 'cpu', 'any', 'qsv', 'nvenc', 'vaapi'];
const GROUP_LABELS: Record<EncoderAvailabilityView['group'], string> = {
	preset: "HandBrake preset's own",
	cpu: 'CPU',
	any: 'Any GPU',
	qsv: 'Intel QSV',
	nvenc: 'NVIDIA NVENC',
	vaapi: 'AMD VAAPI'
};

/** One optgroup of the encoder select. */
export interface EncoderGroup {
	group: EncoderAvailabilityView['group'];
	label: string;
	encoders: EncoderAvailabilityView[];
}

/**
 * The catalog's encoders as the select's optgroups: in GROUP_ORDER, each
 * with its heading and its encoders in catalog order. A group with no
 * encoders is left out, and so is an encoder whose group is not in
 * GROUP_ORDER.
 */
export function encoderGroups(encoders: EncoderAvailabilityView[]): EncoderGroup[] {
	const groups = new Map<string, EncoderAvailabilityView[]>();
	for (const enc of encoders) {
		const list = groups.get(enc.group);
		if (list) list.push(enc);
		else groups.set(enc.group, [enc]);
	}
	return GROUP_ORDER.flatMap((group) => {
		const list = groups.get(group);
		return list ? [{ group, label: GROUP_LABELS[group], encoders: list }] : [];
	});
}
