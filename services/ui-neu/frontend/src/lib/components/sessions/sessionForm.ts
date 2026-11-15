// What the session builder makes of its form: the required-field rules, the
// overrides field read as JSON, and the create and update requests.
import type { MediaType, SessionCreateRequest, SessionUpdateRequest } from '$lib/types/api.gen';
import { NAME_REQUIRED, type FieldErrors } from '$lib/utils/formValidation';

/** The builder's required inputs, by element id, in form order. */
export const SESSION_FIELDS = { name: 'sb-name', rip: 'sb-rip', path: 'sb-path' } as const;
export const SESSION_FIELD_ORDER: string[] = Object.values(SESSION_FIELDS);

export const RIP_PRESET_REQUIRED = 'Choose a rip preset';
export const OUTPUT_PATH_REQUIRED = 'Output path is required';

/** The required fields left empty, each keyed by its input's id. */
export function sessionErrors(form: Pick<SessionForm, 'name' | 'ripId' | 'template'>): FieldErrors {
	const errors: FieldErrors = {};
	if (!form.name) errors[SESSION_FIELDS.name] = NAME_REQUIRED;
	if (!form.ripId) errors[SESSION_FIELDS.rip] = RIP_PRESET_REQUIRED;
	if (!form.template) errors[SESSION_FIELDS.path] = OUTPUT_PATH_REQUIRED;
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
