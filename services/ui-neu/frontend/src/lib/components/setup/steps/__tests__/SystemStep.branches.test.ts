import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, cleanup } from '$lib/testing/render';
import type { SetupView } from '$lib/types/api.gen';

// Branch pin for SystemStep, beside steps-behaviour.test.ts. No branch is
// left open.

vi.mock('$lib/api/system', () => ({ fetchSystemDiagnostics: () => new Promise(() => {}) }));
vi.mock('$lib/api/resources', () => ({ fetchResources: () => new Promise(() => {}) }));

import SystemStep from '../SystemStep.svelte';

const view = { completed_at: null, progress: {}, current_step: 'system' } as unknown as SetupView;
type Step = { commit(): Promise<string | false> };

afterEach(() => cleanup());

describe('SystemStep', () => {
	it('records attention when committed before the health check has reported', async () => {
		const { component } = renderComponent(SystemStep, { props: { view } });
		expect(await screen.findByText('Checking the server...')).toBeInTheDocument();
		expect(await (component as unknown as Step).commit()).toBe('attention');
	});
});
