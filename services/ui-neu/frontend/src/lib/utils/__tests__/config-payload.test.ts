import { describe, it, expect } from 'vitest';
import { buildConfigPayload, mergeConfigValues, mergeSavedPayload } from '../../settings/config-payload';
import { HIDDEN_SECRET } from '$lib/api/config';
import type { ConfigFieldMeta } from '$lib/types/api.gen';

const field = (key: string, tier: 'operator' | 'secret' = 'operator'): ConfigFieldMeta =>
	({ key, group: 'G', tier, label: key, help: '', type: 'string', editable: true }) as ConfigFieldMeta;

const PLAIN = field('name');
const SECRET = field('api_key', 'secret');

describe('buildConfigPayload', () => {
	it('sends a changed field and leaves an unchanged one out', () => {
		const fields = [PLAIN, field('other')];
		const out = buildConfigPayload(fields, { name: 'new', other: 'same' }, { name: 'old', other: 'same' }, {});
		expect(out).toEqual({ name: 'new' });
	});

	it('treats an equal array as unchanged and a different one as changed', () => {
		const fields = [field('a'), field('b')];
		const out = buildConfigPayload(fields, { a: ['x', 'y'], b: ['x'] }, { a: ['x', 'y'], b: ['z'] }, {});
		expect(out).toEqual({ b: ['x'] });
	});

	it.each([
		['the mask', HIDDEN_SECRET],
		['an empty string', ''],
		['null', null],
		['undefined', undefined]
	])('leaves a secret out when it is %s', (_name, value) => {
		expect(buildConfigPayload([SECRET], { api_key: value }, { api_key: 'stored' }, {})).toEqual({});
	});

	it('sends a secret that has a new value', () => {
		expect(buildConfigPayload([SECRET], { api_key: 'fresh' }, { api_key: HIDDEN_SECRET }, {})).toEqual({
			api_key: 'fresh'
		});
	});

	it('leaves out a secret equal to its baseline', () => {
		expect(buildConfigPayload([SECRET], { api_key: 'same' }, { api_key: 'same' }, {})).toEqual({});
	});

	it.each([
		['empty', { api_key: '' }],
		['null', { api_key: null }],
		['missing', {}]
	])('sends a cleared secret that is %s as null', (_name, values) => {
		expect(buildConfigPayload([SECRET], values, { api_key: HIDDEN_SECRET }, { api_key: true })).toEqual({
			api_key: null
		});
	});

	it('sends a cleared secret that was then typed into as typed', () => {
		expect(buildConfigPayload([SECRET], { api_key: 'typed' }, { api_key: HIDDEN_SECRET }, { api_key: true })).toEqual({
			api_key: 'typed'
		});
	});

	it('does not treat a cleared flag on a plain field as a clear', () => {
		expect(buildConfigPayload([PLAIN], { name: '' }, { name: 'old' }, { name: true })).toEqual({ name: '' });
	});

	it('reads only the given fields', () => {
		expect(buildConfigPayload([PLAIN], { name: 'n', extra: 'x' }, {}, {})).toEqual({ name: 'n' });
	});
});

describe('mergeSavedPayload', () => {
	it('makes a saved secret the mask in both the overrides and the values', () => {
		const out = mergeSavedPayload({ api_key: 'raw' }, [SECRET], {}, { api_key: 'raw' });
		expect(out.overrides).toEqual({ api_key: HIDDEN_SECRET });
		expect(out.values).toEqual({ api_key: HIDDEN_SECRET });
	});

	it('keeps a saved plain field as an override and leaves its value as it was', () => {
		const out = mergeSavedPayload({ name: 'new' }, [PLAIN], {}, { name: 'typed' });
		expect(out.overrides).toEqual({ name: 'new' });
		expect(out.values).toEqual({ name: 'typed' });
	});

	it('treats a key with no field as a plain one', () => {
		const out = mergeSavedPayload({ ghost: 1 }, [PLAIN], {}, {});
		expect(out.overrides).toEqual({ ghost: 1 });
		expect(out.values).toEqual({});
	});

	it('keeps the old overrides and values of keys not in the payload', () => {
		const out = mergeSavedPayload({ name: 'new' }, [PLAIN], { other: 'o' }, { other: 'v' });
		expect(out.overrides).toEqual({ other: 'o', name: 'new' });
		expect(out.values).toEqual({ other: 'v' });
	});

	it('does not change its inputs', () => {
		const payload = { api_key: 'raw', name: 'new' };
		const overrides = { name: 'old' };
		const values = { api_key: 'raw' };
		mergeSavedPayload(payload, [SECRET, PLAIN], overrides, values);
		expect(payload).toEqual({ api_key: 'raw', name: 'new' });
		expect(overrides).toEqual({ name: 'old' });
		expect(values).toEqual({ api_key: 'raw' });
	});
});

describe('mergeConfigValues', () => {
	const fields = [field('a'), field('b')];

	it('takes every value from config when nothing is kept, edits or not', () => {
		expect(mergeConfigValues(fields, { a: 1, b: 2 }, null)).toEqual({ a: 1, b: 2 });
	});

	it('keeps an edit to a field whose config value did not change', () => {
		const kept = { config: { a: 1, b: 2 }, values: { a: 'edited', b: 2 } };
		expect(mergeConfigValues(fields, { a: 1, b: 2 }, kept)).toEqual({ a: 'edited', b: 2 });
	});

	it('takes the new config value for a field config changed', () => {
		const kept = { config: { a: 1, b: 2 }, values: { a: 'edited', b: 'edited too' } };
		expect(mergeConfigValues(fields, { a: 1, b: 3 }, kept)).toEqual({ a: 'edited', b: 3 });
	});

	it('takes the config value for a field the kept values do not hold', () => {
		const kept = { config: { a: 1, b: 2 }, values: { a: 'edited' } };
		expect(mergeConfigValues(fields, { a: 1, b: 2 }, kept)).toEqual({ a: 'edited', b: 2 });
	});

	it('counts an equal array in both configs as unchanged', () => {
		const kept = { config: { a: ['x', 'y'] }, values: { a: ['edited'] } };
		expect(mergeConfigValues([field('a')], { a: ['x', 'y'] }, kept)).toEqual({ a: ['edited'] });
	});

	it('puts only the given fields in the result', () => {
		const kept = { config: { a: 1, extra: 1 }, values: { a: 1, extra: 'edited' } };
		expect(mergeConfigValues([field('a')], { a: 1, extra: 2 }, kept)).toEqual({ a: 1 });
	});
});
