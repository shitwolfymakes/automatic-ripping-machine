import { describe, it, expect } from 'vitest';
import { getVideoTypeConfig, discTypeLabel } from '../utils/job-type';

describe('getVideoTypeConfig', () => {
	it('returns fallback for null', () => {
		const config = getVideoTypeConfig(null);
		expect(config.label).toBe('Disc');
		expect(config.icon).toBe('disc');
	});

	it('returns correct config for known types', () => {
		expect(getVideoTypeConfig('movie').label).toBe('Movie');
		expect(getVideoTypeConfig('series').label).toBe('Series');
		expect(getVideoTypeConfig('music').label).toBe('Music');
		expect(getVideoTypeConfig('data').label).toBe('Data');
	});

	it('is case-insensitive', () => {
		expect(getVideoTypeConfig('Movie').label).toBe('Movie');
		expect(getVideoTypeConfig('SERIES').label).toBe('Series');
	});

	it('returns fallback for unknown type', () => {
		expect(getVideoTypeConfig('audiobook').label).toBe('Disc');
	});

	it('uses Video fallback when video_type is unknown but disctype is video', () => {
		// ARM knows it's a video disc, classification still pending - the
		// cyan "Video" pill signals "we know it's video, not what kind"
		// instead of presuming "Movie" or showing generic "Disc".
		const dvd = getVideoTypeConfig(null, 'dvd');
		expect(dvd.label).toBe('Video');
		expect(dvd.accent).toContain('--color-accent-4');
		expect(getVideoTypeConfig('unknown', 'bluray').label).toBe('Video');
		expect(getVideoTypeConfig(undefined, 'bluray4k').label).toBe('Video');
		expect(getVideoTypeConfig(null, 'uhd').label).toBe('Video');
	});

	it('Video fallback is case-insensitive on disctype', () => {
		expect(getVideoTypeConfig(null, 'DVD').label).toBe('Video');
		expect(getVideoTypeConfig(null, 'BluRay').label).toBe('Video');
	});

	it('keeps Disc fallback for non-video disctypes', () => {
		// Data discs and audio CDs that fail metadata lookup should
		// stay on the generic "Disc" pill - not "Video".
		expect(getVideoTypeConfig(null, 'data').label).toBe('Disc');
		expect(getVideoTypeConfig(null, 'music').label).toBe('Disc');
		expect(getVideoTypeConfig(null, '').label).toBe('Disc');
	});

	it('confirmed video_type wins over disctype Video fallback', () => {
		// A movie that happens to be on a DVD still renders as "Movie",
		// not "Video".
		expect(getVideoTypeConfig('movie', 'dvd').label).toBe('Movie');
		expect(getVideoTypeConfig('series', 'bluray').label).toBe('Series');
	});
});

describe('discTypeLabel', () => {
	it('returns Unknown for null and undefined', () => {
		expect(discTypeLabel(null)).toBe('Unknown');
		expect(discTypeLabel(undefined)).toBe('Unknown');
	});

	it('returns proper labels for known disc types', () => {
		expect(discTypeLabel('dvd')).toBe('DVD');
		expect(discTypeLabel('bluray')).toBe('Blu-ray');
		expect(discTypeLabel('bluray4k')).toBe('4K UHD');
		expect(discTypeLabel('cd')).toBe('CD');
		expect(discTypeLabel('music')).toBe('Music CD');
		expect(discTypeLabel('data')).toBe('Data');
		expect(discTypeLabel('unknown')).toBe('Unknown');
	});

	it('is case-insensitive', () => {
		expect(discTypeLabel('DVD')).toBe('DVD');
		expect(discTypeLabel('BluRay')).toBe('Blu-ray');
	});

	it('returns input as-is for unknown types', () => {
		expect(discTypeLabel('laserdisc')).toBe('laserdisc');
	});
});
