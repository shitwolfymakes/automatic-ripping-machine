import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup } from '$lib/testing/render';
import AutoSaveToggle from '../AutoSaveToggle.svelte';

afterEach(cleanup);

const PROPS = {
	key: 'auto_transcode_on_idle',
	label: 'Apply these defaults automatically after each rip',
	help: 'When a rip completes, apply its default session.'
};

describe('AutoSaveToggle', () => {
	it('renders the field as a switch with its label, help and anchor, and says it saves on its own', () => {
		renderComponent(AutoSaveToggle, { props: { ...PROPS, checked: true, ontoggle: vi.fn() } });
		const toggle = screen.getByRole('switch', { name: PROPS.label });
		expect(toggle).toHaveAttribute('aria-checked', 'true');
		expect(screen.getByText(PROPS.help)).toBeInTheDocument();
		expect(screen.getByText('(changes save automatically)')).toBeInTheDocument();
		expect(screen.getByTestId('setting-auto_transcode_on_idle')).toHaveAttribute(
			'id',
			'setting-auto_transcode_on_idle'
		);
		expect(screen.queryByRole('button', { name: 'Save' })).not.toBeInTheDocument();
	});

	it('reports the flipped value on click', async () => {
		const ontoggle = vi.fn();
		renderComponent(AutoSaveToggle, { props: { ...PROPS, checked: false, ontoggle } });
		await fireEvent.click(screen.getByRole('switch', { name: PROPS.label }));
		expect(ontoggle).toHaveBeenCalledWith(true);
	});

	it('leaves out the help line when there is none', () => {
		renderComponent(AutoSaveToggle, {
			props: { key: 'notifications_enabled', label: 'Enable notifications', checked: false, ontoggle: vi.fn() }
		});
		expect(screen.getByTestId('setting-notifications_enabled').querySelector('.field-help')).toBeNull();
	});
});
