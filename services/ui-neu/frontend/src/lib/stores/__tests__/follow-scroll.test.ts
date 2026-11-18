import { describe, expect, it } from 'vitest';
import { FollowScroll } from '../follow-scroll.svelte';

function makeView(scrollTop: number): HTMLDivElement {
	const view = document.createElement('div');
	Object.defineProperty(view, 'scrollHeight', { value: 1000, configurable: true });
	Object.defineProperty(view, 'clientHeight', { value: 200, configurable: true });
	Object.defineProperty(view, 'scrollTop', { value: scrollTop, configurable: true, writable: true });
	return view;
}

describe('FollowScroll', () => {
	describe('onScroll', () => {
		it('keeps following at 23px from the bottom', () => {
			const view = makeView(777);
			const follow = new FollowScroll(() => view);
			follow.following = false;
			follow.onScroll();
			expect(follow.following).toBe(true);
		});

		it('pauses at 24px from the bottom', () => {
			const view = makeView(776);
			const follow = new FollowScroll(() => view);
			follow.onScroll();
			expect(follow.following).toBe(false);
		});

		it('counts no view as at the bottom', () => {
			const follow = new FollowScroll(() => null);
			follow.following = false;
			follow.onScroll();
			expect(follow.following).toBe(true);
		});
	});

	describe('jumpToLatest', () => {
		it('follows and scrolls the view to the bottom', () => {
			const view = makeView(0);
			const follow = new FollowScroll(() => view);
			follow.following = false;
			follow.jumpToLatest();
			expect(follow.following).toBe(true);
			expect(view.scrollTop).toBe(1000);
		});

		it('still follows with no view', () => {
			const follow = new FollowScroll(() => null);
			follow.following = false;
			follow.jumpToLatest();
			expect(follow.following).toBe(true);
		});
	});

	describe('sync', () => {
		it('clears the count and scrolls to the bottom while following', () => {
			const view = makeView(0);
			const follow = new FollowScroll(() => view);
			follow.newWhilePaused = 4;
			follow.sync(3, view, true);
			expect(follow.newWhilePaused).toBe(0);
			expect(view.scrollTop).toBe(1000);
		});

		it('counts growth while paused, nothing without growth, and lowers seen when the total shrinks', () => {
			const view = makeView(0);
			const follow = new FollowScroll(() => view);
			follow.sync(8, view, true);
			follow.following = false;
			follow.sync(10, view, false);
			expect(follow.newWhilePaused).toBe(2);
			follow.sync(10, view, false);
			expect(follow.newWhilePaused).toBe(2);
			follow.sync(5, view, false);
			expect(follow.newWhilePaused).toBe(2);
			follow.sync(6, view, false);
			expect(follow.newWhilePaused).toBe(3);
		});

		it('starts following on the first view bound while paused, and changes nothing else', () => {
			const view = makeView(0);
			const follow = new FollowScroll(() => view);
			follow.following = false;
			follow.newWhilePaused = 2;
			follow.sync(7, view, false);
			expect(follow.following).toBe(true);
			expect(follow.newWhilePaused).toBe(2);
			expect(view.scrollTop).toBe(0);
			follow.sync(9, view, false);
			expect(follow.newWhilePaused).toBe(4);
		});

		it('clears the count when a new view binds while following', () => {
			const view = makeView(0);
			const follow = new FollowScroll(() => view);
			follow.newWhilePaused = 3;
			follow.sync(4, view, true);
			expect(follow.newWhilePaused).toBe(0);
			expect(view.scrollTop).toBe(1000);
		});

		it('does not rebind the same view', () => {
			const view = makeView(0);
			const follow = new FollowScroll(() => view);
			follow.sync(1, view, true);
			follow.following = false;
			follow.sync(2, view, false);
			expect(follow.following).toBe(false);
			expect(follow.newWhilePaused).toBe(1);
		});

		it('unbinds on a null view and changes nothing else', () => {
			const view = makeView(0);
			const follow = new FollowScroll(() => view);
			follow.sync(2, view, true);
			follow.following = false;
			follow.sync(2, null, false);
			expect(follow.following).toBe(false);
			expect(follow.newWhilePaused).toBe(0);
			follow.sync(2, view, false);
			expect(follow.following).toBe(true);
		});
	});
});
