import { describe, it, expect } from 'vitest';
import { LANGUAGES, canonicalValue, choiceLabel, findChoice, languageChoices, unchosenChoices } from '../languages';

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

	it('carries every entry of HandBrake 1.11.1 libhb/lang.c, undetermined included', () => {
		expect(LANGUAGES).toHaveLength(187);
		expect(LANGUAGES.find((l) => l.code === 'und')?.name).toBe('Unknown');
	});

	it('stores the T code and keeps the B code as an alias that is never itself a code', () => {
		expect(LANGUAGES.find((l) => l.code === 'fra')).toMatchObject({ name: 'French', alias: 'fre' });
		expect(LANGUAGES.find((l) => l.code === 'deu')?.alias).toBe('ger');
		expect(LANGUAGES.find((l) => l.code === 'zho')?.alias).toBe('chi');
		const codes = new Set(LANGUAGES.map((l) => l.code));
		const aliases = LANGUAGES.flatMap((l) => (l.alias ? [l.alias] : []));
		expect(new Set(aliases).size).toBe(aliases.length);
		expect(aliases.some((a) => codes.has(a))).toBe(false);
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
	it('finds French by its B alias and reports the T code', () => {
		expect(findChoice(choices, 'fre')?.value).toBe('fra');
		expect(findChoice(choices, 'French (fra)')?.value).toBe('fra');
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

	it('labels a stored B code as its language', () => {
		expect(choiceLabel(languageChoices('AudioLanguageList'), 'fre')).toBe('French (fra)');
	});
});

describe('canonicalValue and unchosenChoices', () => {
	const choices = languageChoices('SubtitleLanguageList')!;
	it('maps an alias to its code and leaves other values alone', () => {
		expect(canonicalValue(choices, 'fre')).toBe('fra');
		expect(canonicalValue(choices, 'fra')).toBe('fra');
		expect(canonicalValue(choices, 'zzz')).toBe('zzz');
		expect(canonicalValue(null, 'fre')).toBe('fre');
	});
	it('leaves out a choice a stored value names by code or alias', () => {
		const left = unchosenChoices(choices, ['fre', 'eng', 'zzz']).map((c) => c.value);
		expect(left).not.toContain('fra');
		expect(left).not.toContain('eng');
		expect(left).toContain('deu');
		expect(left).toHaveLength(choices.length - 2);
	});
});
