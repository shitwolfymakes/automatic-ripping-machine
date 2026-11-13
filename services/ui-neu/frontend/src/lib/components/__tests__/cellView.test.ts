import { describe, expect, it } from 'vitest';
import { alignClass, cellView } from '$lib/components/data-table';

describe('alignClass', () => {
	it('right-aligns end columns only', () => {
		expect(alignClass('end')).toBe('data-table-num');
		expect(alignClass('start')).toBe('');
		expect(alignClass()).toBe('');
	});
});

describe('cellView', () => {
	it('plain text carries a title and the base text class', () => {
		const v = cellView({ text: 'hello' });
		expect(v).toEqual({
			className: '',
			title: 'hello',
			text: 'hello',
			sub: undefined,
			pill: undefined,
			badges: undefined,
			textClass: 'data-table-text',
			muted: undefined
		});
	});

	it('mono text adds the mono class', () => {
		expect(cellView({ text: '/a/b', mono: true }).textClass).toBe('data-table-text mono');
	});

	it('muted cells set data-muted', () => {
		expect(cellView({ text: 'x', muted: true }).muted).toBe('true');
	});

	it('end alignment sets the numeric class', () => {
		expect(cellView({ text: '1' }, 'end').className).toBe('data-table-num');
		expect(cellView({ text: '1' }, 'start').className).toBe('');
	});

	it('passes the sub line and badges through', () => {
		const badges = [{ text: 'b', tone: 'warn' as const }];
		const v = cellView({ text: 't', sub: 's', badges });
		expect(v.sub).toBe('s');
		expect(v.badges).toBe(badges);
	});

	it('media tones become a media pill with no title', () => {
		const v = cellView({ text: 'Movie', pill: { tone: 'movie' } });
		expect(v.pill).toEqual({ kind: 'media', tone: 'movie', text: 'Movie' });
		expect(v.title).toBeUndefined();
	});

	it('custom and builtin tones become a tag pill', () => {
		expect(cellView({ text: 'Custom', pill: { tone: 'custom' } }).pill).toEqual({
			kind: 'tag',
			tone: 'custom',
			text: 'Custom'
		});
		expect(cellView({ text: 'Built-in', pill: { tone: 'builtin' } }).pill?.kind).toBe('tag');
	});
});
