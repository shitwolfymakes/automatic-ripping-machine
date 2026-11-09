// One radio group of segment buttons in the log terminal's toolbar, rendered directly.
import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup } from '$lib/test-utils';
import LogSegmentGroup from '../LogSegmentGroup.svelte';

type Defaults = NonNullable<Parameters<typeof renderComponent>[1]>;

const OPTIONS = [
	{ key: 'all', label: 'All' },
	{ key: 'ripper', label: 'Ripper' },
	{ key: 'backend', label: 'Backend' }
];

function renderGroup(props: Record<string, unknown> = {}) {
	const onpick = vi.fn();
	const view = renderComponent(LogSegmentGroup, {
		props: { label: 'Log filter', options: OPTIONS, value: 'all', testid: 'seg', onpick, ...props }
	} as Defaults);
	return { onpick, ...view };
}

describe('LogSegmentGroup', () => {
	afterEach(cleanup);

	it('is a radiogroup named by its label', () => {
		renderGroup();
		expect(screen.getByRole('radiogroup', { name: 'Log filter' })).toBeInTheDocument();
	});

	it('draws one radio per option, in order, with its label and testid', () => {
		renderGroup();
		const radios = screen.getAllByRole('radio');
		expect(radios.map((r) => r.textContent)).toEqual(['All', 'Ripper', 'Backend']);
		expect(radios.map((r) => r.getAttribute('data-testid'))).toEqual(['seg-all', 'seg-ripper', 'seg-backend']);
	});

	it('checks only the radio whose key is the value', () => {
		renderGroup({ value: 'ripper' });
		const radios = screen.getAllByRole('radio');
		expect(radios.map((r) => r.getAttribute('aria-checked'))).toEqual(['false', 'true', 'false']);
	});

	it('calls onpick with the clicked segment key', async () => {
		const { onpick } = renderGroup();
		await fireEvent.click(screen.getByTestId('seg-backend'));
		expect(onpick).toHaveBeenCalledTimes(1);
		expect(onpick).toHaveBeenCalledWith('backend');
	});

	it('moves aria-checked when rerendered with a new value', async () => {
		const { rerender } = renderGroup({ value: 'all' });
		expect(screen.getByTestId('seg-all')).toHaveAttribute('aria-checked', 'true');
		await rerender({ label: 'Log filter', options: OPTIONS, value: 'backend', testid: 'seg', onpick: vi.fn() });
		expect(screen.getByTestId('seg-all')).toHaveAttribute('aria-checked', 'false');
		expect(screen.getByTestId('seg-backend')).toHaveAttribute('aria-checked', 'true');
	});
});
