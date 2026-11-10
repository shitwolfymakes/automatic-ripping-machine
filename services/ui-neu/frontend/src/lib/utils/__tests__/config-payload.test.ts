import { describe, it, expect } from 'vitest';
import { buildConfigPayload } from '../config-payload';
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
