import { describe, it, expect } from 'vitest';
import { TitleEditDraft } from '../title-edit-draft.svelte';
import type { MetadataCandidate } from '$lib/types/api.gen';

function candidate(over: Partial<MetadataCandidate> = {}): MetadataCandidate {
	return { title: 'Alien', year: 1979, kind: 'movie', poster_url: 'https://img/a.jpg', ...over };
}

describe('TitleEditDraft', () => {
	it('starts closed with empty fields', () => {
		const d = new TitleEditDraft();
		expect(d.editing).toBe(false);
		expect(d.title).toBe('');
		expect(d.year).toBe('');
		expect(d.type).toBe('movie');
		expect(d.posterUrl).toBe('');
		expect(d.posterEdited).toBe(false);
	});

	describe('fill', () => {
		it('copies a full row into the fields and clears the poster flag', () => {
			const d = new TitleEditDraft();
			d.posterEdited = true;
			d.fill(candidate());
			expect(d.title).toBe('Alien');
			expect(d.year).toBe('1979');
			expect(d.type).toBe('movie');
			expect(d.posterUrl).toBe('https://img/a.jpg');
			expect(d.posterEdited).toBe(false);
		});

		it('uses blank year and poster when the row has none', () => {
			const d = new TitleEditDraft();
			d.fill(candidate({ year: null, poster_url: null }));
			expect(d.year).toBe('');
			expect(d.posterUrl).toBe('');
		});

		it('maps tv and series kinds to series and movie to movie', () => {
			const d = new TitleEditDraft();
			d.fill(candidate({ kind: 'tv' }));
			expect(d.type).toBe('series');
			d.fill(candidate({ kind: 'series' }));
			expect(d.type).toBe('series');
			d.fill(candidate({ kind: 'movie' }));
			expect(d.type).toBe('movie');
		});
	});

	describe('toggle', () => {
		it('opens and fills, then closes keeping the text', () => {
			const d = new TitleEditDraft();
			d.toggle(candidate());
			expect(d.editing).toBe(true);
			expect(d.title).toBe('Alien');
			d.title = 'Aliens';
			d.toggle(candidate());
			expect(d.editing).toBe(false);
			expect(d.title).toBe('Aliens');
		});
	});

	describe('close', () => {
		it('closes and clears the poster flag but keeps the text', () => {
			const d = new TitleEditDraft();
			d.toggle(candidate());
			d.posterEdited = true;
			d.close();
			expect(d.editing).toBe(false);
			expect(d.posterEdited).toBe(false);
			expect(d.title).toBe('Alien');
		});
	});

	describe('posterIsManual', () => {
		it.each([
			[false, false, false],
			[false, true, false],
			[true, false, false],
			[true, true, true]
		])('editing=%s posterEdited=%s gives %s', (editing, posterEdited, expected) => {
			const d = new TitleEditDraft();
			d.editing = editing;
			d.posterEdited = posterEdited;
			expect(d.posterIsManual).toBe(expected);
		});
	});

	describe('values while closed', () => {
		it('returns the match with its year and poster', () => {
			const d = new TitleEditDraft();
			d.title = 'ignored';
			expect(d.values(candidate())).toEqual({
				title: 'Alien',
				year: '1979',
				isSeries: false,
				poster: 'https://img/a.jpg'
			});
		});

		it('returns blank year, null poster and the series kind when missing', () => {
			const d = new TitleEditDraft();
			expect(d.values(candidate({ year: null, poster_url: null, kind: 'tv' }))).toEqual({
				title: 'Alien',
				year: '',
				isSeries: true,
				poster: null
			});
		});
	});

	describe('values while open', () => {
		function open(): TitleEditDraft {
			const d = new TitleEditDraft();
			d.editing = true;
			d.title = '  Aliens ';
			d.year = ' 1986 ';
			d.type = 'series';
			d.posterUrl = ' https://img/b.jpg ';
			return d;
		}

		it('returns the trimmed fields as a series with the typed poster', () => {
			const d = open();
			d.posterEdited = true;
			expect(d.values(candidate())).toEqual({
				title: 'Aliens',
				year: '1986',
				isSeries: true,
				poster: 'https://img/b.jpg'
			});
		});

		it('returns a movie when the type is movie', () => {
			const d = open();
			d.type = 'movie';
			expect(d.values(candidate()).isSeries).toBe(false);
		});

		it('returns null for a typed blank poster', () => {
			const d = open();
			d.posterEdited = true;
			d.posterUrl = '   ';
			expect(d.values(candidate()).poster).toBeNull();
		});

		it("keeps the match's poster when the poster is untouched", () => {
			expect(open().values(candidate()).poster).toBe('https://img/a.jpg');
		});

		it('gives a null poster when untouched and the match has none', () => {
			expect(open().values(candidate({ poster_url: null })).poster).toBeNull();
		});
	});
});
