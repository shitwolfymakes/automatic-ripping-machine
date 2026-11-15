import { describe, it, expect } from 'vitest';
import { LANGUAGES, choiceLabel, findChoice, languageChoices } from '../languages';

describe('LANGUAGES', () => {
	it('has unique three-letter codes with names', () => {
		const codes = LANGUAGES.map((l) => l.code);
		expect(new Set(codes).size).toBe(codes.length);
		for (const l of LANGUAGES) {
			expect(l.code).toMatch(/^[a-z]{3}$/);
			expect(l.name).not.toBe('');
		}
		expect(LANGUAGES.find((l) => l.code === 'eng')?.name).toBe('English');
	});
});

describe('languageChoices', () => {
	it('offers any first for audio only', () => {
		const audio = languageChoices('AudioLanguageList')!;
		expect(audio[0]).toEqual({ value: 'any', label: 'Any language' });
		expect(audio).toHaveLength(LANGUAGES.length + 1);
		const subtitles = languageChoices('SubtitleLanguageList')!;
		expect(subtitles.some((c) => c.value === 'any')).toBe(false);
		expect(subtitles).toHaveLength(LANGUAGES.length);
	});

	it('is null for other keys', () => {
		expect(languageChoices('AudioCopyMask')).toBeNull();
	});
});

describe('findChoice', () => {
	const choices = languageChoices('SubtitleLanguageList')!;
	it.each(['English (eng)', 'ENG', ' english '])('finds English by %j', (text) => {
		expect(findChoice(choices, text)?.value).toBe('eng');
	});
	it('finds nothing for unknown text', () => {
		expect(findChoice(choices, 'klingon')).toBeUndefined();
		expect(findChoice(choices, 'Engl')).toBeUndefined();
	});
});

describe('choiceLabel', () => {
	it('labels a known value and falls back to the raw value', () => {
		const choices = languageChoices('AudioLanguageList');
		expect(choiceLabel(choices, 'eng')).toBe('English (eng)');
		expect(choiceLabel(choices, 'zzz')).toBe('zzz');
		expect(choiceLabel(null, 'eng')).toBe('eng');
	});
});
