import { describe, it, expect, afterEach } from 'vitest';
import { flushSync, tick } from 'svelte';
import { renderComponent, screen, fireEvent, cleanup } from '$lib/testing/render';
import FlyoutHarness from './FlyoutHarness.svelte';

// Branch pins for Flyout, beside Flyout.svelte.test.ts. Every branch is
// reachable, so none is left open: the `if (!root) return;` guard in place()
// is reached by unmounting right after opening, because the queued
// tick().then(place) then runs with root already unset.

afterEach(cleanup);

/** The span Flyout measures: the trigger button's parent. */
function rootSpan(): HTMLElement {
	return screen.getByTestId('trigger').parentElement as HTMLElement;
}

function stubRect(el: HTMLElement, rect: { left: number; right: number; bottom: number }) {
	el.getBoundingClientRect = () => ({ ...rect, top: 0, width: 0, height: 0, x: 0, y: 0, toJSON: () => ({}) });
}

describe('alignment', () => {
	it('left alignment anchors the panel to the trigger left edge with no right style', async () => {
		renderComponent(FlyoutHarness, { props: { align: 'left' } });
		stubRect(rootSpan(), { left: 120, right: 200, bottom: 40 });
		await fireEvent.click(screen.getByTestId('trigger'));
		const panel = screen.getByRole('menu');
		expect(panel.style.left).toBe('120px');
		expect(panel.style.right).toBe('');
	});

	it('left alignment keeps an 8px margin when the trigger is flush with the edge', async () => {
		renderComponent(FlyoutHarness, { props: { align: 'left' } });
		stubRect(rootSpan(), { left: 2, right: 50, bottom: 40 });
		await fireEvent.click(screen.getByTestId('trigger'));
		expect(screen.getByRole('menu').style.left).toBe('8px');
	});

	it('right alignment sets a right style and no left style', async () => {
		renderComponent(FlyoutHarness);
		stubRect(rootSpan(), { left: 120, right: window.innerWidth - 30, bottom: 40 });
		await fireEvent.click(screen.getByTestId('trigger'));
		const panel = screen.getByRole('menu');
		expect(panel.style.right).toBe('30px');
		expect(panel.style.left).toBe('');
	});
});

describe('repositioning', () => {
	it.each(['scroll', 'resize'])('a window %s moves the open panel to the new trigger rect', async (type) => {
		renderComponent(FlyoutHarness, { props: { align: 'left' } });
		stubRect(rootSpan(), { left: 100, right: 150, bottom: 40 });
		await fireEvent.click(screen.getByTestId('trigger'));
		expect(screen.getByRole('menu').style.left).toBe('100px');

		stubRect(rootSpan(), { left: 300, right: 350, bottom: 90 });
		await fireEvent(window, new Event(type));
		const panel = screen.getByRole('menu');
		expect(panel.style.left).toBe('300px');
		expect(panel.style.top).toBe('96px');
	});

	it('unmounting right after opening lets the queued re-measure run with no root', async () => {
		const { unmount } = renderComponent(FlyoutHarness);
		screen.getByTestId('trigger').click();
		flushSync();
		unmount();
		// Let the queued tick().then(place) run inside this test, so a throw
		// from it would fail here.
		await tick();
		expect(screen.queryByRole('menu')).toBeNull();
	});
});

describe('keys', () => {
	it('a key other than Escape leaves the panel open', async () => {
		renderComponent(FlyoutHarness);
		await fireEvent.click(screen.getByTestId('trigger'));
		await fireEvent.keyDown(document, { key: 'a' });
		expect(screen.getByRole('menu')).toBeInTheDocument();
	});
});

describe('open effect listeners', () => {
	it('a click inside the trigger or the panel does not close it', async () => {
		renderComponent(FlyoutHarness);
		await fireEvent.click(screen.getByTestId('trigger'));
		// The trigger toggles on click, so click its wrapper span instead.
		await fireEvent.click(rootSpan());
		expect(screen.getByRole('menu')).toBeInTheDocument();
		await fireEvent.click(screen.getByRole('menu'));
		expect(screen.getByRole('menu')).toBeInTheDocument();
	});

	it('a click elsewhere closes it', async () => {
		renderComponent(FlyoutHarness);
		await fireEvent.click(screen.getByTestId('trigger'));
		await fireEvent.click(screen.getByTestId('outside'));
		expect(screen.queryByRole('menu')).toBeNull();
	});

	it('once closed, an outside click, a scroll and Escape do nothing', async () => {
		renderComponent(FlyoutHarness);
		await fireEvent.click(screen.getByTestId('trigger'));
		await fireEvent.click(screen.getByTestId('outside'));
		expect(screen.queryByRole('menu')).toBeNull();

		await fireEvent.click(screen.getByTestId('outside'));
		await fireEvent(window, new Event('scroll'));
		await fireEvent.keyDown(document, { key: 'Escape' });
		expect(screen.queryByRole('menu')).toBeNull();
		expect(screen.getByTestId('trigger')).toHaveAttribute('aria-expanded', 'false');
	});
});
