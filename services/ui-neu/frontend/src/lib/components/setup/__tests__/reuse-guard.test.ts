import { describe, it, expect } from 'vitest';

// Setup spec D5: the walkthrough composes the components Settings uses and
// never implements a setting itself. A step file may read (getters) but every
// write goes through a shared component's own save().
const sources = import.meta.glob('../steps/*.svelte', { query: '?raw', import: 'default', eager: true }) as Record<
	string,
	string
>;

const ALLOWED_API = new Set([
	'$lib/api/setup',
	'$lib/api/drives',
	'$lib/api/system',
	'$lib/api/resources',
	'$lib/api/iso',
	'$lib/api/gpus',
	'$lib/api/channels',
	'$lib/api/users',
	'$lib/api/config',
	'$lib/api/ws'
]);
const WRITES =
	/\b(saveArmConfig|updateDrive|enrollDrive|ignoreDrive|unignoreDrive|updateGpu|deleteGpu|probeGpu|probeAllGpus|createChannel|updateChannel|setUserDisabled|setUserPassword|changePassword|completeSetup|putSetupStep|restartSetup)\s*\(|\b(post|patch|put|del|apiFetch)\s*[<(]/;

describe('setup steps reuse shared components', () => {
	it('found all nine step files', () => expect(Object.keys(sources)).toHaveLength(9));

	for (const [file, src] of Object.entries(sources)) {
		it(`${file.split('/').pop()} makes no direct fetch or API write`, () => {
			expect(src).not.toMatch(/\bfetch\s*\(/);
			expect(src).not.toMatch(WRITES);
			for (const m of src.matchAll(/from '(\$lib\/api\/[^']+)'/g)) expect(ALLOWED_API).toContain(m[1]);
			expect(src).not.toMatch(/<input[^>]+(api_key|makemkv_key|auto_rip_on_insert)/);
		});
	}
});
