// What the session builder makes of its form: the overrides field read
// as JSON, and the create and update requests.
import type { MediaType, SessionCreateRequest, SessionUpdateRequest } from '$lib/types/api.gen';

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
