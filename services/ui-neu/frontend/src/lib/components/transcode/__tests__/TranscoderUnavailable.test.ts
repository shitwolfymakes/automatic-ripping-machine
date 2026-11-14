import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, screen, cleanup } from '$lib/test-utils';
import TranscoderUnavailable from '../TranscoderUnavailable.svelte';

afterEach(() => {
	cleanup();
});

describe('TranscoderUnavailable', () => {
	it('shows the page title and the unavailable text', () => {
		renderComponent(TranscoderUnavailable, { heldTasks: 0 });
		expect(screen.getByRole('heading', { name: 'Transcoder' })).toBeInTheDocument();
		expect(screen.getByTestId('transcoder-unavailable')).toHaveTextContent(
			'Transcoding is not available on this deployment (ripper-only install).'
		);
	});

	it('shows no held-tasks alert at 0', () => {
		renderComponent(TranscoderUnavailable, { heldTasks: 0 });
		expect(screen.queryByTestId('transcoder-held-encode-tasks')).not.toBeInTheDocument();
	});

	it('says "1 encode task is held" at 1', () => {
		renderComponent(TranscoderUnavailable, { heldTasks: 1 });
		expect(screen.getByTestId('transcoder-held-encode-tasks')).toHaveTextContent('1 encode task is held');
	});

	it('says "3 encode tasks are held" at 3', () => {
		renderComponent(TranscoderUnavailable, { heldTasks: 3 });
		expect(screen.getByTestId('transcoder-held-encode-tasks')).toHaveTextContent('3 encode tasks are held');
	});
});
