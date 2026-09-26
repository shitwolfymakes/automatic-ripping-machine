import { it, expect } from 'vitest';
import { encoderSummary } from '../encoders';

it('summarizes the tool-own encoder as nothing', () => {
	expect(encoderSummary('preset')).toBe('');
	expect(encoderSummary(null)).toBe('');
	expect(encoderSummary(undefined)).toBe('');
});

it('summarizes a catalog encoder by its label', () => {
	expect(encoderSummary('any_h265')).toBe('Any GPU H.265');
	expect(encoderSummary('vaapi_av1')).toBe('AMD VAAPI AV1');
});

it('falls back to the raw id for an encoder the list does not know', () => {
	expect(encoderSummary('future_x')).toBe('future_x');
});
