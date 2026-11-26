import { describe, it, expect, vi, afterEach } from 'vitest';
import { onOutsideClick } from '../outside-click';

function el(): HTMLElement {
	const node = document.createElement('div');
	document.body.appendChild(node);
	return node;
}

const stops: (() => void)[] = [];

function listen(...args: Parameters<typeof onOutsideClick>) {
	const stop = onOutsideClick(...args);
	stops.push(stop);
	return stop;
}

afterEach(() => {
	stops.splice(0).forEach((stop) => stop());
	document.body.innerHTML = '';
});

describe('onOutsideClick', () => {
	it('calls the handler for an event outside every node', () => {
		const a = el();
		const b = el();
		const outside = el();
		const handler = vi.fn();
		listen('click', () => [a, b], handler);
		outside.dispatchEvent(new MouseEvent('click', { bubbles: true }));
		expect(handler).toHaveBeenCalledTimes(1);
	});

	it('does not call the handler for an event inside any node', () => {
		const a = el();
		const b = el();
		const child = document.createElement('span');
		b.appendChild(child);
		const handler = vi.fn();
		listen('click', () => [a, b], handler);
		a.dispatchEvent(new MouseEvent('click', { bubbles: true }));
		child.dispatchEvent(new MouseEvent('click', { bubbles: true }));
		expect(handler).not.toHaveBeenCalled();
	});

	it('counts an unset node as not containing the target', () => {
		const a = el();
		const outside = el();
		const handler = vi.fn();
		listen('click', () => [undefined, null], handler);
		outside.dispatchEvent(new MouseEvent('click', { bubbles: true }));
		expect(handler).toHaveBeenCalledTimes(1);
		listen('click', () => [undefined, a, null], handler);
		a.dispatchEvent(new MouseEvent('click', { bubbles: true }));
		expect(handler).toHaveBeenCalledTimes(2);
	});

	it('asks inside at event time, so a node added later counts', () => {
		const a = el();
		const later = el();
		const nodes: Node[] = [a];
		const handler = vi.fn();
		listen('click', () => nodes, handler);
		nodes.push(later);
		later.dispatchEvent(new MouseEvent('click', { bubbles: true }));
		expect(handler).not.toHaveBeenCalled();
	});

	it('listens in the capture phase, so a stopped inner press still counts', () => {
		const inner = el();
		inner.addEventListener('mousedown', (ev) => ev.stopPropagation());
		const handler = vi.fn();
		listen('mousedown', () => [], handler);
		inner.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
		expect(handler).toHaveBeenCalledTimes(1);
	});

	it('ignores events of another type', () => {
		const outside = el();
		const handler = vi.fn();
		listen('mousedown', () => [], handler);
		outside.dispatchEvent(new MouseEvent('click', { bubbles: true }));
		expect(handler).not.toHaveBeenCalled();
	});

	it('stops calling the handler after the returned function runs', () => {
		const outside = el();
		const handler = vi.fn();
		const stop = listen('click', () => [], handler);
		stop();
		outside.dispatchEvent(new MouseEvent('click', { bubbles: true }));
		expect(handler).not.toHaveBeenCalled();
	});
});
