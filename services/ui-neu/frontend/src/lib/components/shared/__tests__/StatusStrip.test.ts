import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, screen, cleanup } from '$lib/test-utils';
import StatusStrip from '../StatusStrip.svelte';

describe('StatusStrip', () => {
	afterEach(() => cleanup());

	it('renders title, detail and the server message in mono as a status region', () => {
		renderComponent(StatusStrip, {
			props: {
				tone: 'danger',
				title: "The ripper for this drive didn't start.",
				detail: 'Other drives are not affected.',
				message: 'device /dev/sr2 is busy'
			}
		});
		const region = screen.getByRole('status');
		expect(region).toHaveAttribute('data-tone', 'danger');
		expect(region).toHaveTextContent("The ripper for this drive didn't start.");
		expect(screen.getByText('device /dev/sr2 is busy')).toHaveClass('mono');
	});

	it('shows a progress bar only when asked', () => {
		const { container } = renderComponent(StatusStrip, {
			props: { tone: 'busy', title: 'Starting ripper...', progress: true }
		});
		expect(container.querySelector('.status-strip-bar')).not.toBeNull();
	});
});
