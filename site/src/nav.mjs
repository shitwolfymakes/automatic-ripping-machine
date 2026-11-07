// Resolves the manifest nav's link items and drops, with an error, those that don't resolve.

const NAV_SCHEMES = new Set(['http', 'https', 'mailto']);

// Why a resolved nav link can't go in the nav (resolver error, unsupported scheme, missing anchor), or null when it can.
export function navItemError(target, resolved, headingIdsById) {
	if (resolved.kind === 'error') return resolved.message;
	if (resolved.kind === 'external' && !NAV_SCHEMES.has(resolved.url.split(':')[0].toLowerCase())) {
		return `unsupported link scheme: ${target}`;
	}
	if (resolved.kind === 'page' && resolved.fragment && !headingIdsById.get(resolved.id)?.has(resolved.fragment)) {
		return `missing anchor #${resolved.fragment} in ${resolved.id}`;
	}
	return null;
}

// Resolves every nav item to its link target; items that fail to resolve are dropped and reported in `errors`.
export function resolveNav(nav, resolver, errors, headingIdsById) {
	return nav.map((section) => ({
		...section,
		groups: section.groups.map((g) => ({
			...g,
			items: g.items.flatMap((item) => {
				if (item.pageId) return [{ label: item.label, resolved: { kind: 'page', id: item.pageId, fragment: '' } }];
				const resolved = resolver.resolve(item.target, item.from);
				const error = navItemError(item.target, resolved, headingIdsById);
				if (error !== null) {
					errors.push(`${item.where}: ${error}`);
					return [];
				}
				return [{ label: item.label, resolved }];
			})
		}))
	}));
}
