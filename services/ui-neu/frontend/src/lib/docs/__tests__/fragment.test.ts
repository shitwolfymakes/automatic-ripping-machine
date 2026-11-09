import { describe, it, expect, vi, afterEach } from 'vitest';
import { fragmentId, scrollToFragment } from '../fragment';

describe('fragmentId', () => {
	it('drops the leading # from a plain hash', () => {
		expect(fragmentId('#install')).toBe('install');
	});

	it('returns an empty id for an empty hash', () => {
		expect(fragmentId('')).toBe('');
	});

	it('decodes a percent-encoded hash', () => {
		expect(fragmentId('#a%20b')).toBe('a b');
	});

	it('returns a malformed percent-encoded hash raw', () => {
		expect(fragmentId('#%E0%A4%A')).toBe('%E0%A4%A');
	});
});

describe('scrollToFragment', () => {
	const added: HTMLElement[] = [];

	function addElement(tag: string, id?: string) {
		const el = document.createElement(tag);
		if (id) el.id = id;
		document.body.appendChild(el);
		added.push(el);
		return el;
	}

	afterEach(() => {
		for (const el of added.splice(0)) el.remove();
	});

	it('scrolls the element with the id into view', () => {
		const el = addElement('h2', 'install');
		el.scrollIntoView = vi.fn();
		scrollToFragment('install');
		expect(el.scrollIntoView).toHaveBeenCalledOnce();
	});

	it('does nothing when no element has the id', () => {
		const main = addElement('main');
		main.scrollTo = vi.fn();
		expect(() => scrollToFragment('missing')).not.toThrow();
		expect(main.scrollTo).not.toHaveBeenCalled();
	});

	it('scrolls <main> to the top for an empty id', () => {
		const main = addElement('main');
		main.scrollTo = vi.fn();
		scrollToFragment('');
		expect(main.scrollTo).toHaveBeenCalledWith(0, 0);
	});

	it('does nothing for an empty id when there is no <main>', () => {
		expect(() => scrollToFragment('')).not.toThrow();
	});
});
