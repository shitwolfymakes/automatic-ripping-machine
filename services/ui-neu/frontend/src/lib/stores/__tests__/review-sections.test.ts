import { describe, it, expect } from 'vitest';
import { ReviewSections } from '$lib/stores/review-sections.svelte';

describe('ReviewSections', () => {
	describe('open', () => {
		it('opens a section', () => {
			const s = new ReviewSections();
			s.open('music');
			expect(s.active).toBe('music');
		});

		it('closes the first section when another opens', () => {
			const s = new ReviewSections();
			s.open('music');
			s.open('episodes');
			expect(s.active).toBe('episodes');
			expect(s.isOpen('music')).toBe(false);
		});

		it('closes every section when given null', () => {
			const s = new ReviewSections();
			s.open('info');
			s.open(null);
			expect(s.active).toBeNull();
		});

		it('clears infoFocus when a section other than info opens', () => {
			const s = new ReviewSections();
			s.infoFocus = 'season';
			s.open('title');
			expect(s.infoFocus).toBeNull();
		});

		it('keeps infoFocus when info opens', () => {
			const s = new ReviewSections();
			s.infoFocus = 'season';
			s.open('info');
			expect(s.infoFocus).toBe('season');
		});
	});

	describe('isOpen', () => {
		it('is true for the open section and false for another', () => {
			const s = new ReviewSections();
			s.open('title');
			expect(s.isOpen('title')).toBe(true);
			expect(s.isOpen('info')).toBe(false);
		});
	});

	describe('toggle', () => {
		it('opens a closed section', () => {
			const s = new ReviewSections();
			s.toggle('info');
			expect(s.active).toBe('info');
		});

		it('closes the open section', () => {
			const s = new ReviewSections();
			s.toggle('info');
			s.toggle('info');
			expect(s.active).toBeNull();
		});

		it('switches to another section', () => {
			const s = new ReviewSections();
			s.toggle('info');
			s.toggle('music');
			expect(s.active).toBe('music');
		});

		it('resets titleInitialType when the title search opens', () => {
			const s = new ReviewSections();
			s.titleInitialType = 'tv';
			s.toggle('title');
			expect(s.active).toBe('title');
			expect(s.titleInitialType).toBeUndefined();
		});

		it('resets titleInitialType when the title search closes', () => {
			const s = new ReviewSections();
			s.toggle('title');
			s.titleInitialType = 'tv';
			s.toggle('title');
			expect(s.active).toBeNull();
			expect(s.titleInitialType).toBeUndefined();
		});

		it('leaves titleInitialType alone when another section toggles', () => {
			const s = new ReviewSections();
			s.titleInitialType = 'tv';
			s.toggle('music');
			expect(s.titleInitialType).toBe('tv');
		});
	});

	describe('openSeason', () => {
		it('opens info with infoFocus season', () => {
			const s = new ReviewSections();
			s.openSeason();
			expect(s.active).toBe('info');
			expect(s.infoFocus).toBe('season');
		});
	});

	describe('searchSeries', () => {
		it('opens the title search for tv and clears infoFocus', () => {
			const s = new ReviewSections();
			s.openSeason();
			s.searchSeries();
			expect(s.active).toBe('title');
			expect(s.titleInitialType).toBe('tv');
			expect(s.infoFocus).toBeNull();
		});
	});

	describe('close', () => {
		it('closes the open section', () => {
			const s = new ReviewSections();
			s.open('episodes');
			s.close('episodes');
			expect(s.active).toBeNull();
		});

		it('changes nothing for a section that is not open', () => {
			const s = new ReviewSections();
			s.openSeason();
			s.titleInitialType = 'tv';
			s.close('episodes');
			expect(s.active).toBe('info');
			expect(s.infoFocus).toBe('season');
			expect(s.titleInitialType).toBe('tv');
		});
	});
});
