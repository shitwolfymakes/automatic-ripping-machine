import type { ConfigView } from '$lib/types/api.gen';

/** What the stubbed SetupConfigFields reports at mount and after a save. */
export const stubState: { atMount: ConfigView | null; afterSave: ConfigView | null } = {
	atMount: null,
	afterSave: null
};
