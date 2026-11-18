import { describe, expect, it } from 'vitest';
import registry from '../field-docs.json';
import { FIELD_IDS as session } from '$lib/sessions/session-form';
import { FIELD_IDS as ripPreset } from '$lib/sessions/rip-preset-form';
import { FIELD_IDS as transcodePreset } from '$lib/handbrake/panel-view';
import { FIELD_IDS as drive } from '$lib/drives/settings';
import { FIELD_IDS as users } from '$lib/settings/users-form';
import { FIELD_IDS as iface } from '$lib/settings/interface-form';
import { FIELD_IDS as changePassword } from '$lib/utils/password';
import { FIELD_IDS as notifyChannel } from '$lib/notifications/channel-form';

// Coverage of the hand-written forms: every id a form declares in its
// FIELD_IDS has a registry entry, and every form.* entry belongs to a form.
//
// The forms are listed here by hand rather than collected with an eager
// import.meta.glob over src/lib: that would import every module in the tree,
// running each store's and client's module-level setup inside the test. The
// raw-source scan below keeps the list honest instead: a module that exports
// FIELD_IDS but is missing here fails the test.
const FORMS: Record<string, Record<string, string>> = {
	'/src/lib/sessions/session-form.ts': session,
	'/src/lib/sessions/rip-preset-form.ts': ripPreset,
	'/src/lib/handbrake/panel-view.ts': transcodePreset,
	'/src/lib/drives/settings.ts': drive,
	'/src/lib/settings/users-form.ts': users,
	'/src/lib/settings/interface-form.ts': iface,
	'/src/lib/utils/password.ts': changePassword,
	'/src/lib/notifications/channel-form.ts': notifyChannel
};

const sources = import.meta.glob(['/src/lib/**/*.ts', '!/src/lib/**/__tests__/**'], {
	query: '?raw',
	import: 'default',
	eager: true
}) as Record<string, string>;

const FIELDS = registry.fields as Record<string, unknown>;
const declared = Object.values(FORMS).flatMap((ids) => Object.values(ids));

describe('hand-written form field ids', () => {
	it('lists every module that exports FIELD_IDS', () => {
		const exporting = Object.keys(sources).filter((file) => /^export const FIELD_IDS\b/m.test(sources[file]));
		expect(exporting.sort()).toEqual(Object.keys(FORMS).sort());
	});

	it('names each field by its form under the form. prefix', () => {
		const misnamed = declared.filter((id) => !/^form\.[a-z_]+\.[a-z_]+$/.test(id));
		expect(misnamed).toEqual([]);
	});

	it('gives every declared id a registry entry', () => {
		const missing = declared.filter((id) => !(id in FIELDS));
		expect(missing).toEqual([]);
	});

	it('keeps no form.* entry that no form declares', () => {
		const orphans = Object.keys(FIELDS).filter((id) => id.startsWith('form.') && !declared.includes(id));
		expect(orphans).toEqual([]);
	});

	it('declares each id once', () => {
		expect(new Set(declared).size).toBe(declared.length);
	});
});
