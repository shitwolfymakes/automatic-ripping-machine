import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, cleanup } from '$lib/test-utils';
import type { ConfigView, SetupView } from '$lib/types/api.gen';
import { stubState } from './fixtures/setup-config-fields-stub';

vi.mock('../../SetupConfigFields.svelte', async () => ({
	default: (await import('./fixtures/SetupConfigFieldsStub.svelte')).default
}));

import MakemkvStep from '../MakemkvStep.svelte';

const view = { completed_at: null, progress: {}, current_step: 'makemkv' } as unknown as SetupView;
const cfg = (valid: boolean | null) => ({ makemkv_key_valid: valid }) as unknown as ConfigView;
type Step = { commit(): Promise<string | false> };

afterEach(() => cleanup());

describe('MakemkvStep (D-109)', () => {
	it('records attention when the key was rejected after the step opened', async () => {
		stubState.atMount = cfg(null);
		stubState.afterSave = cfg(false);
		const { component } = renderComponent(MakemkvStep, { props: { view } });
		expect(await (component as unknown as Step).commit()).toBe('attention');
	});

	it('records done when a key invalid at mount has since been accepted', async () => {
		stubState.atMount = cfg(false);
		stubState.afterSave = cfg(true);
		const { component } = renderComponent(MakemkvStep, { props: { view } });
		expect(await (component as unknown as Step).commit()).toBe('done');
	});
});
