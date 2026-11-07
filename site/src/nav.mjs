// Resolves the manifest nav's link items and drops, with an error, those that don't resolve.

const NAV_SCHEMES = new Set(['http', 'https', 'mailto']);

// Resolves every nav item to its link target; items that fail to resolve are dropped and reported in `errors`.
export function resolveNav(nav, resolver, errors, headingIdsById) {
	return nav.map((section) => ({
		...section,
		groups: section.groups.map((g) => ({
			...g,
			items: g.items.flatMap((item) => {
				if (item.pageId) return [{ label: item.label, resolved: { kind: 'page', id: item.pageId, fragment: '' } }];
				const resolved = resolver.resolve(item.target, item.from);
				if (resolved.kind === 'error') {
					errors.push(`${item.where}: ${resolved.message}`);
					return [];
				}
				if (resolved.kind === 'external' && !NAV_SCHEMES.has(resolved.url.split(':')[0].toLowerCase())) {
					errors.push(`${item.where}: unsupported link scheme: ${item.target}`);
					return [];
				}
				if (resolved.kind === 'page' && resolved.fragment && !headingIdsById.get(resolved.id)?.has(resolved.fragment)) {
					errors.push(`${item.where}: missing anchor #${resolved.fragment} in ${resolved.id}`);
					return [];
				}
				return [{ label: item.label, resolved }];
			})
		}))
	}));
}
