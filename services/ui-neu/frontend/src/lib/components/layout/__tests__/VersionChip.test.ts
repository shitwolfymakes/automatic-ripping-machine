import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderComponent, screen, waitFor, cleanup } from '$lib/testing/render';

let respond: () => Promise<unknown> = () => Promise.resolve({ version: '0' });
let calls = 0;
vi.mock('$lib/api/system', () => ({
	fetchSystemVersion: () => {
		calls += 1;
		return respond();
	}
}));

import VersionChip from '../VersionChip.svelte';
import { DEFAULT_REPO_URL, VERSION_CHIP_TIMEOUT_MS } from '$lib/layout/version-chip';

describe('VersionChip', () => {
	beforeEach(() => {
		calls = 0;
	});
	afterEach(() => {
		cleanup();
		vi.useRealTimers();
	});

	it('shows the green status when up to date', async () => {
		respond = () => Promise.resolve({ version: '2.10.1', latest_version: '2.10.1', update_available: false });
		renderComponent(VersionChip);
		expect(await screen.findByText('v2.10.1')).toBeTruthy();
		expect(screen.getByText('Up to date')).toBeTruthy();
		expect(screen.queryByRole('link', { name: /Update available/ })).toBeNull();
		const link = screen.getByRole('link', { name: 'ARM v2.10.1 on GitHub (opens in a new tab)' });
		expect(link.getAttribute('href')).toBe(DEFAULT_REPO_URL);
		expect(link.getAttribute('target')).toBe('_blank');
		expect(link.getAttribute('rel')).toBe('noopener noreferrer');
	});

	it('links to the repo_url the backend reports', async () => {
		respond = () => Promise.resolve({ version: '2.10.1', repo_url: 'https://github.com/me/fork' });
		renderComponent(VersionChip);
		const link = await screen.findByRole('link', { name: 'ARM v2.10.1 on GitHub (opens in a new tab)' });
		expect(link.getAttribute('href')).toBe('https://github.com/me/fork');
	});

	it('does not double a leading v', async () => {
		respond = () => Promise.resolve({ version: 'v2.10.1' });
		renderComponent(VersionChip);
		expect(await screen.findByText('v2.10.1')).toBeTruthy();
	});

	it('links to the release when an update is available', async () => {
		respond = () =>
			Promise.resolve({
				version: '2.10.1',
				latest_version: '2.11.0',
				update_available: true,
				release_url: 'https://github.com/o/r/releases/tag/v2.11.0'
			});
		renderComponent(VersionChip);
		const link = await screen.findByRole('link', { name: 'Update available: v2.11.0 (opens in a new tab)' });
		expect(link.getAttribute('href')).toBe('https://github.com/o/r/releases/tag/v2.11.0');
		expect(screen.queryByText('Up to date')).toBeNull();
		expect(link.textContent).toContain('Update available');
	});

	it('shows the version alone, linked to the repo, when the release url is not a GitHub page', async () => {
		respond = () =>
			Promise.resolve({
				version: '2.10.1',
				latest_version: '2.11.0',
				update_available: true,
				release_url: 'javascript:alert(document.domain)'
			});
		renderComponent(VersionChip);
		const link = await screen.findByRole('link', { name: 'ARM v2.10.1 on GitHub (opens in a new tab)' });
		expect(link.getAttribute('href')).toBe(DEFAULT_REPO_URL);
		expect(screen.queryByText('Update available')).toBeNull();
	});

	it('shows the version alone when nothing was checked', async () => {
		respond = () => Promise.resolve({ version: '2.10.1', latest_version: null, update_available: null });
		renderComponent(VersionChip);
		expect(await screen.findByText('v2.10.1')).toBeTruthy();
		expect(screen.queryByText('Up to date')).toBeNull();
		expect(screen.queryByRole('link', { name: /Update available/ })).toBeNull();
	});

	it('fetches once and reports settled once the version arrives', async () => {
		respond = () => Promise.resolve({ version: '2.10.1' });
		const onsettled = vi.fn();
		renderComponent(VersionChip, { props: { onsettled } });
		await screen.findByText('v2.10.1');
		expect(calls).toBe(1);
		expect(onsettled).toHaveBeenCalledTimes(1);
	});

	it('draws nothing and still reports settled when the fetch fails', async () => {
		respond = () => Promise.reject(new Error('boom'));
		const onsettled = vi.fn();
		const { container } = renderComponent(VersionChip, { props: { onsettled } });
		await waitFor(() => expect(onsettled).toHaveBeenCalledTimes(1));
		expect(container.querySelector('[data-version-chip]')).toBeNull();
	});

	it('gives up after the timeout when the fetch never answers, so the panel is not held back', async () => {
		vi.useFakeTimers();
		respond = () => new Promise(() => {});
		const onsettled = vi.fn();
		const { container } = renderComponent(VersionChip, { props: { onsettled } });
		await vi.advanceTimersByTimeAsync(VERSION_CHIP_TIMEOUT_MS - 1);
		expect(onsettled).not.toHaveBeenCalled();
		await vi.advanceTimersByTimeAsync(1);
		expect(onsettled).toHaveBeenCalledTimes(1);
		expect(container.querySelector('[data-version-chip]')).toBeNull();
	});
});
