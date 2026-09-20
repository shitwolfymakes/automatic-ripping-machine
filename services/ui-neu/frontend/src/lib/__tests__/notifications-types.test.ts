import { describe, it, expect } from 'vitest';
import { isCatalogField } from '$lib/types/notifications';

describe('notification types', () => {
	it('isCatalogField accepts a well-formed field', () => {
		expect(isCatalogField({ key: 'tts', label: 'TTS', type: 'bool', private: false, required: false })).toBe(true);
	});

	it('isCatalogField rejects a missing key', () => {
		expect(isCatalogField({ label: 'TTS', type: 'bool' })).toBe(false);
	});
});
