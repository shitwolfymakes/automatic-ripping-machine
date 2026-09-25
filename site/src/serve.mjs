#!/usr/bin/env node
// Serves build/site under a base path, mimicking GitHub Pages' project URL
// (https://<owner>.github.io/arm-v3/). Verification only.
import { createServer } from 'node:http';
import { createReadStream, existsSync, statSync } from 'node:fs';
import { dirname, extname, join, normalize, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';

const { values } = parseArgs({ options: { base: { type: 'string', default: '/arm-v3/' }, port: { type: 'string', default: '4173' }, dir: { type: 'string' } } });
const root = resolve(values.dir ?? join(dirname(fileURLToPath(import.meta.url)), '../build/site'));
const base = values.base.endsWith('/') ? values.base : `${values.base}/`;
const TYPES = { '.html': 'text/html; charset=utf-8', '.css': 'text/css', '.js': 'text/javascript', '.json': 'application/json', '.woff2': 'font/woff2', '.ico': 'image/x-icon', '.png': 'image/png', '.jpg': 'image/jpeg', '.svg': 'image/svg+xml' };

createServer((req, res) => {
	const { pathname } = new URL(req.url, 'http://localhost');
	if (!pathname.startsWith(base)) {
		res.writeHead(302, { location: base });
		return res.end();
	}
	let file = normalize(join(root, decodeURIComponent(pathname.slice(base.length))));
	if (!file.startsWith(root)) {
		res.writeHead(403);
		return res.end();
	}
	if (existsSync(file) && statSync(file).isDirectory()) file = join(file, 'index.html');
	if (!existsSync(file)) {
		res.writeHead(404);
		return res.end('not found');
	}
	res.writeHead(200, { 'content-type': TYPES[extname(file)] ?? 'application/octet-stream' });
	createReadStream(file).pipe(res);
}).listen(Number(values.port), () => console.log(`http://localhost:${values.port}${base}`));
