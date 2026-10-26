import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, cleanup } from '$lib/test-utils';
import type { SetupView } from '$lib/types/api.gen';

vi.mock('$lib/api/settings', () => ({ fetchSettings: () => Promise.reject(new Error('offline')) }));

import MetadataStep from '../MetadataStep.svelte';

const view: SetupView = {
	completed_at: null,
	progress: {},
	current_step: 'metadata',
	admin_default_password: false,
	checklist_dismissed: false
};

afterEach(() => cleanup());

describe('MetadataStep', () => {
	it('lists the four keyless sources under Already working', () => {
		renderComponent(MetadataStep, { props: { view } });
		for (const name of ['TVmaze', 'MusicBrainz', 'ARM community database (CRC64)', 'TheDiscDB disc map']) {
			expect(screen.getByText(name)).toBeInTheDocument();
		}
		expect(screen.getAllByText('No key needed')).toHaveLength(4);
	});
});
