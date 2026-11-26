// The rip preset form's fields, including its custom track filters, in the
// field docs registry.
export const FIELD_IDS = {
	name: 'form.rip_preset.name',
	media_type: 'form.rip_preset.media_type',
	track_selection: 'form.rip_preset.track_selection',
	identification_mode: 'form.rip_preset.identification_mode',
	output_mode: 'form.rip_preset.output_mode',
	min_duration: 'form.rip_preset.min_duration',
	max_duration: 'form.rip_preset.max_duration',
	title_allowlist: 'form.rip_preset.title_allowlist',
	title_blocklist: 'form.rip_preset.title_blocklist'
} as const;
