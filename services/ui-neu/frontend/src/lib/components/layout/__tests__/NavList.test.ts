import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup } from '$lib/testing/render';
import NavList from '../NavList.svelte';

const items = [
	{ href: '/', label: 'Dashboard', icon: 'M0 0' },
	{ href: '/notifications', label: 'Notifications', icon: 'M1 1' },
	{ href: '/logs', label: 'Logs', icon: 'M2 2' }
];

function render(props: Record<string, unknown> = {}) {
	return renderComponent(NavList, { props: { items, pathname: '/logs', notificationCount: null, ...props } });
}

describe('NavList', () => {
	afterEach(() => cleanup());

	it('renders one link per item with its icon path and label', () => {
		const { container } = render();
		const links = screen.getAllByRole('link');
		expect(links.map((a) => a.getAttribute('href'))).toEqual(['/', '/notifications', '/logs']);
		expect(links[1]).toHaveTextContent('Notifications');
		expect(container.querySelectorAll('nav.nav path')[2]).toHaveAttribute('d', 'M2 2');
	});

	it('marks only the active item', () => {
		render();
		const [dash, notif, logs] = screen.getAllByRole('link');
		expect(logs).toHaveAttribute('data-active', 'true');
		expect(dash).not.toHaveAttribute('data-active');
		expect(notif).not.toHaveAttribute('data-active');
	});

	it('shows the badge on notifications when the count is positive', () => {
		const { container } = render({ notificationCount: 3 });
		const badges = container.querySelectorAll('.nav-badge');
		expect(badges).toHaveLength(1);
		expect(badges[0]).toHaveTextContent('3');
		expect(screen.getByRole('link', { name: /notifications/i })).toContainElement(badges[0] as HTMLElement);
	});

	it.each([null, 0])('hides the badge when the count is %s', (notificationCount) => {
		const { container } = render({ notificationCount });
		expect(container.querySelector('.nav-badge')).toBeNull();
	});

	it('calls onnavigate when a link is clicked', async () => {
		const onnavigate = vi.fn();
		render({ onnavigate });
		await fireEvent.click(screen.getByRole('link', { name: /logs/i }));
		expect(onnavigate).toHaveBeenCalledTimes(1);
	});

	it('clicks without a handler do nothing', async () => {
		render();
		await expect(fireEvent.click(screen.getByRole('link', { name: /logs/i }))).resolves.toBeDefined();
	});
});
