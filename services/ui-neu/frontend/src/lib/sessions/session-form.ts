// What the session builder makes of its form: the field rules, the
// overrides field read as JSON, and the create and update requests.
import type { MediaType, SessionCreateRequest, SessionUpdateRequest } from '$lib/types/api.gen';
import { NAME_REQUIRED, type FieldErrors } from '$lib/ui/form-validation';

/** The builder's checked inputs, by element id, in form order. */
export const SESSION_FIELDS = { name: 'sb-name', rip: 'sb-rip', path: 'sb-path', overrides: 'sb-overrides' } as const;
export const SESSION_FIELD_ORDER: string[] = Object.values(SESSION_FIELDS);

/** The builder's fields in the field docs registry. */
export const FIELD_IDS = {
	name: 'form.session.name',
	media_type: 'form.session.media_type',
	rip_preset: 'form.session.rip_preset',
	transcode_preset: 'form.session.transcode_preset',
	output_path: 'form.session.output_path',
	overrides: 'form.session.overrides'
} as const;

export const RIP_PRESET_REQUIRED = 'Choose a rip preset';
export const OUTPUT_PATH_REQUIRED = 'Output path is required';
export const OVERRIDES_INVALID = 'Invalid JSON in overrides field';

/** The builder's inputs as typed, before the overrides text is parsed. */
export interface SessionInputs {
	name: string;
	ripId: string;
	template: string;
	overridesText: string;
}

function overridesValid(text: string): boolean {
	try {
		parseOverrides(text);
		return true;
	} catch {
		return false;
	}
}

/** The required fields left empty and an overrides text that is not JSON, each keyed by its input's id. */
export function sessionErrors(inputs: SessionInputs): FieldErrors {
	const errors: FieldErrors = {};
	if (!inputs.name) errors[SESSION_FIELDS.name] = NAME_REQUIRED;
	if (!inputs.ripId) errors[SESSION_FIELDS.rip] = RIP_PRESET_REQUIRED;
	if (!inputs.template) errors[SESSION_FIELDS.path] = OUTPUT_PATH_REQUIRED;
	if (!overridesValid(inputs.overridesText)) errors[SESSION_FIELDS.overrides] = OVERRIDES_INVALID;
	return errors;
}

/** The overrides field's value: null when it is blank, its JSON
 * otherwise. Throws a SyntaxError when the text is not JSON. */
export function parseOverrides(text: string): Record<string, unknown> | null {
	return text.trim() ? JSON.parse(text) : null;
}

/** The builder's form, as the requests read it. */
export interface SessionForm {
	name: string;
	mediaType: MediaType;
	ripId: string;
	/** The transcode preset's id, or '' for none. */
	tcId: string;
	template: string;
	overrides: Record<string, unknown> | null;
}

/** The update request for the form. It leaves out media_type, which
 * can't change on edit: the update schema has no such field, so it is
 * not sent rather than left for the backend to drop. */
export function sessionUpdate(form: SessionForm) {
	return {
		name: form.name,
		rip_preset_id: form.ripId,
		transcode_preset_id: form.tcId || null,
		output_path_template: form.template,
		overrides_json: form.overrides
	} satisfies SessionUpdateRequest;
}

/** The create request for the form: the update's fields and the media
 * type. */
export function sessionCreate(form: SessionForm): SessionCreateRequest {
	return { ...sessionUpdate(form), media_type: form.mediaType };
}
