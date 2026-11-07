// Parses and validates the build CLI's command-line options.
import { join, resolve } from 'node:path';
import { parseArgs } from 'node:util';

// The build's options from the CLI args: target (all, site or app), verbose, and the resolved out and appOut dirs.
export function parseOptions(args, siteDir) {
	const { values } = parseArgs({
		args,
		options: {
			target: { type: 'string', default: 'all' },
			out: { type: 'string', default: join(siteDir, 'build') },
			'app-out': { type: 'string' },
			verbose: { type: 'boolean', default: false }
		}
	});
	const { target, verbose } = values;
	if (!['all', 'site', 'app'].includes(target)) throw new Error(`--target must be all, site or app (got ${target})`);
	const out = resolve(values.out);
	return { target, verbose, out, appOut: resolve(values['app-out'] ?? join(out, 'app')) };
}
