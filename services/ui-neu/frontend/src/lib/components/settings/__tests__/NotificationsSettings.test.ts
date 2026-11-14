import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, cleanup, fireEvent } from '$lib/testing/render';
import NotificationsSettings from '../NotificationsSettings.svelte';

// NotificationsTab fetches on mount; its calls are faked so the component
// renders without a network.
vi.mock('$lib/api/channels', () => ({
	fetchChannels: vi.fn(() => Promise.resolve([])),
	fetchServices: vi.fn(() => Promise.resolve({ featured: [], services: [] })),
	fetchEventTypes: vi.fn(() => Promise.resolve([])),
	fetchDispatches: vi.fn(() => Promise.resolve([])),
	createChannel: vi.fn(),
	updateChannel: vi.fn(),
	deleteChannel: vi.fn(),
	testSendChannel: vi.fn(),
	composeUrl: vi.fn(),
	testConfig: vi.fn()
}));

afterEach(cleanup);

const master = () => screen.getByRole('switch', { name: /enable notifications/i });
const disabledHint = () => screen.queryByText(/notifications are disabled/i);

describe('NotificationsSettings', () => {
	it('renders the heading, description and autosave hint', () => {
		renderComponent(NotificationsSettings, { enabled: false, ontoggle: vi.fn() });
		expect(screen.getByRole('heading', { name: 'Notifications' })).toBeInTheDocument();
		expect(screen.getByText(/manage notification channels/i)).toBeInTheDocument();
		expect(screen.getByText('(changes save automatically)')).toBeInTheDocument();
	});

	it('shows the switch off and the disabled hint without channels when disabled', () => {
		const { container } = renderComponent(NotificationsSettings, { enabled: false, ontoggle: vi.fn() });
		expect(master()).toHaveAttribute('aria-checked', 'false');
		expect(disabledHint()).toBeInTheDocument();
		expect(container.querySelector('.notifications-tab')).toBeNull();
	});

	it('shows the switch on and the channels area without the hint when enabled', () => {
		const { container } = renderComponent(NotificationsSettings, { enabled: true, ontoggle: vi.fn() });
		expect(master()).toHaveAttribute('aria-checked', 'true');
		expect(disabledHint()).toBeNull();
		expect(container.querySelector('.notifications-tab')).not.toBeNull();
	});

	it('calls ontoggle with true when the switch is turned on', async () => {
		const ontoggle = vi.fn();
		renderComponent(NotificationsSettings, { enabled: false, ontoggle });
		await fireEvent.click(master());
		expect(ontoggle).toHaveBeenCalledWith(true);
	});

	it('calls ontoggle with false when the switch is turned off', async () => {
		const ontoggle = vi.fn();
		renderComponent(NotificationsSettings, { enabled: true, ontoggle });
		await fireEvent.click(master());
		expect(ontoggle).toHaveBeenCalledWith(false);
	});
});
