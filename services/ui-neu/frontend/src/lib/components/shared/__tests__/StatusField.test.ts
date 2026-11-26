import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, screen, cleanup } from '$lib/testing/render';
import StatusField from '../StatusField.svelte';

afterEach(cleanup);

describe('StatusField', () => {
	it('labels a status strip and passes its tone, title and message through', () => {
		renderComponent(StatusField, {
			props: { label: 'Key status', tone: 'ok', title: 'Valid', message: 'checked by Test Drive' }
		});
		expect(screen.getByText('Key status')).toHaveClass('status-field-label');
		const strip = screen.getByRole('status');
		expect(strip).toHaveAttribute('data-tone', 'ok');
		expect(strip).toHaveTextContent('Valid');
		expect(strip).toHaveTextContent('checked by Test Drive');
	});
});
