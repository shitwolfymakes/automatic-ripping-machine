// Collects, renders and checks the docs pages and nav.
import { collectPages } from './collect.mjs';
import { createResolver, checkFragments } from './links.mjs';
import { resolveNav } from './nav.mjs';
import { createRenderer } from './render.mjs';

// Collects the manifest's pages, renders them, and resolves the nav, returning every error found, in order.
export async function buildDocs(armRoot, manifest) {
	const { pages, nav, errors } = collectPages(armRoot, manifest);
	const resolver = createResolver({ armRoot, pages, manifest });
	const renderer = await createRenderer();
	const rendered = pages.map((p) => renderer.render(p, resolver));
	errors.push(...rendered.flatMap((r) => r.errors), ...checkFragments(rendered));
	const headingIdsById = new Map(rendered.map((r) => [r.page.id, r.headingIds]));
	const resolvedNav = resolveNav(nav, resolver, errors, headingIdsById);
	return { pages, rendered, nav: resolvedNav, errors };
}

// One "<srcPath>:<line>: <raw>" line per link to a repo file the docs don't publish (it links to GitHub).
export function repoLinkLines(rendered) {
	return rendered.flatMap((r) =>
		r.links.filter((l) => l.resolved.kind === 'repo').map((l) => `${r.page.srcPath}:${l.line}: ${l.raw}`)
	);
}
