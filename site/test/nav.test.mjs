import { test } from 'node:test';
import assert from 'node:assert/strict';
import { resolveNav } from '../src/nav.mjs';

function fakeResolver(table) {
	const calls = [];
	return { calls, resolve: (target, from) => (calls.push([target, from]), table[target]) };
}

function navOf(...items) {
	return [{ title: 'S', groups: [{ title: 'G', items }] }];
}

function itemsOf(nav) {
	return nav[0].groups[0].items;
}

function run(items, table = {}, headings = new Map()) {
	const errors = [];
	const resolver = fakeResolver(table);
	const nav = resolveNav(navOf(...items), resolver, errors, headings);
	return { nav, errors, resolver };
}

test('resolveNav: a pageId item becomes a page link without calling the resolver', () => {
	const { nav, errors, resolver } = run([{ label: 'Home', pageId: 'guide/home' }]);
	assert.deepEqual(itemsOf(nav), [{ label: 'Home', resolved: { kind: 'page', id: 'guide/home', fragment: '' } }]);
	assert.deepEqual(errors, []);
	assert.deepEqual(resolver.calls, []);
});

test('resolveNav: a resolver error is reported with its location and the item dropped', () => {
	const table = { 'x.md': { kind: 'error', message: 'no such page' } };
	const { nav, errors } = run([{ label: 'X', target: 'x.md', from: 'a.md', where: 'manifest[0]' }], table);
	assert.deepEqual(itemsOf(nav), []);
	assert.deepEqual(errors, ['manifest[0]: no such page']);
});

test('resolveNav: http, https and mailto links are kept, whatever the scheme case', () => {
	const urls = ['https://a.example', 'http://b.example', 'mailto:me@example.com', 'HTTPS://C.EXAMPLE'];
	const table = Object.fromEntries(urls.map((url) => [url, { kind: 'external', url }]));
	const { nav, errors } = run(urls.map((url) => ({ label: url, target: url, from: 'm', where: 'w' })), table);
	assert.deepEqual(errors, []);
	assert.deepEqual(itemsOf(nav), urls.map((url) => ({ label: url, resolved: { kind: 'external', url } })));
});

test('resolveNav: an external link with another scheme is reported and dropped', () => {
	const target = 'javascript:alert(1)';
	const table = { [target]: { kind: 'external', url: target } };
	const { nav, errors } = run([{ label: 'J', target, from: 'm', where: 'w1' }], table);
	assert.deepEqual(itemsOf(nav), []);
	assert.deepEqual(errors, [`w1: unsupported link scheme: ${target}`]);
});

test('resolveNav: a page link without a fragment is kept', () => {
	const resolved = { kind: 'page', id: 'guide/a', fragment: '' };
	const { nav, errors } = run([{ label: 'A', target: 'a.md', from: 'm', where: 'w' }], { 'a.md': resolved });
	assert.deepEqual(errors, []);
	assert.deepEqual(itemsOf(nav), [{ label: 'A', resolved }]);
});

test('resolveNav: a page link whose fragment is a known heading is kept', () => {
	const resolved = { kind: 'page', id: 'guide/a', fragment: 'intro' };
	const headings = new Map([['guide/a', new Set(['intro'])]]);
	const item = { label: 'A', target: 'a.md#intro', from: 'm', where: 'w' };
	const { nav, errors } = run([item], { 'a.md#intro': resolved }, headings);
	assert.deepEqual(errors, []);
	assert.deepEqual(itemsOf(nav), [{ label: 'A', resolved }]);
});

test('resolveNav: a page link with a missing fragment is reported, also when the page has no headings entry', () => {
	const resolved = { kind: 'page', id: 'guide/a', fragment: 'gone' };
	const item = { label: 'A', target: 'a.md#gone', from: 'm', where: 'w' };
	const other = new Map([['guide/a', new Set(['intro'])]]);
	for (const headings of [other, new Map()]) {
		const { nav, errors } = run([item], { 'a.md#gone': resolved }, headings);
		assert.deepEqual(itemsOf(nav), []);
		assert.deepEqual(errors, ['w: missing anchor #gone in guide/a']);
	}
});

test('resolveNav: the resolver receives the item target and from', () => {
	const { resolver } = run([{ label: 'A', target: 'a.md', from: 'docs/m.md', where: 'w' }], {
		'a.md': { kind: 'page', id: 'guide/a', fragment: '' }
	});
	assert.deepEqual(resolver.calls, [['a.md', 'docs/m.md']]);
});

test('resolveNav: other kinds pass through', () => {
	const resolved = { kind: 'repo', path: 'services/backend' };
	const { nav, errors } = run([{ label: 'R', target: 'r', from: 'm', where: 'w' }], { r: resolved });
	assert.deepEqual(errors, []);
	assert.deepEqual(itemsOf(nav), [{ label: 'R', resolved }]);
});

test('resolveNav: keeps section and group fields and reports errors in item order', () => {
	const bad = (n) => ({ label: n, target: n, from: 'm', where: n });
	const fail = (message) => ({ kind: 'error', message });
	const table = { a: fail('1'), b: fail('2'), c: fail('3') };
	const nav = [
		{ title: 'S1', icon: 'i1', groups: [{ title: 'G1', open: true, items: [bad('a'), bad('b')] }] },
		{ title: 'S2', groups: [{ title: 'G2', items: [bad('c')] }, { title: 'G3', items: [] }] }
	];
	const errors = [];
	const out = resolveNav(nav, fakeResolver(table), errors, new Map());
	assert.deepEqual(errors, ['a: 1', 'b: 2', 'c: 3']);
	assert.deepEqual(out, [
		{ title: 'S1', icon: 'i1', groups: [{ title: 'G1', open: true, items: [] }] },
		{ title: 'S2', groups: [{ title: 'G2', items: [] }, { title: 'G3', items: [] }] }
	]);
});
