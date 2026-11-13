// The output path field's talk with the template preview endpoint: the
// latest expansion, the one with optional values empty, and any error.
import { previewTemplate } from '$lib/api/sessions';
import type { TemplatePreviewRequest } from '$lib/types/api.gen';
import { errorMessage } from '$lib/utils/errors';

export class TemplatePreview {
	/** The template filled with sample values, or null when there is none. */
	expansion = $state<string | null>(null);
	/**
	 * The expansion with every optional token left empty, or null when it has
	 * none.
	 */
	expansionWithoutOptional = $state<string | null>(null);
	/** Why the last preview failed, or null. */
	error = $state<string | null>(null);
	#timer: ReturnType<typeof setTimeout> | undefined;

	/**
	 * Previews 300 ms from now, dropping a preview already waiting. The
	 * request is built when the wait ends, so it reads the form as it is
	 * then.
	 */
	schedule = (request: () => TemplatePreviewRequest): void => {
		this.cancel();
		this.#timer = setTimeout(async () => {
			try {
				const result = await previewTemplate(request());
				this.expansion = result.expansion;
				this.expansionWithoutOptional = result.expansion_without_optional ?? null;
				this.error = null;
			} catch (err) {
				this.error = errorMessage(err, String(err));
				this.expansion = null;
				this.expansionWithoutOptional = null;
			}
		}, 300);
	};

	/** Drops the preview waiting to run, if there is one. */
	cancel = (): void => {
		clearTimeout(this.#timer);
	};

	/** Forgets the last preview, for a blank template. */
	clear = (): void => {
		this.expansion = null;
		this.expansionWithoutOptional = null;
		this.error = null;
	};
}
