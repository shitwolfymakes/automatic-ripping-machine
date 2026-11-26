// How the notification service picker lists the Apprise catalog: its
// two groups, and a search over it.
import type { Catalog, CatalogService } from '$lib/types/notifications';

/** The picker's two groups: the featured services in the catalog's
 * order, skipping ids it doesn't list, then every other service by
 * name. */
export function serviceGroups(catalog: Catalog): { featured: CatalogService[]; rest: CatalogService[] } {
	const byId = new Map(catalog.services.map((s) => [s.id, s]));
	const featured = catalog.featured.map((id) => byId.get(id)).filter((s): s is CatalogService => !!s);
	const rest = catalog.services
		.filter((s) => !catalog.featured.includes(s.id))
		.sort((a, b) => a.name.localeCompare(b.name));
	return { featured, rest };
}

/** The services whose names contain the search, ignoring case and
 * surrounding spaces; null for a blank search, so the picker shows
 * its groups instead. */
export function matchingServices(catalog: Catalog, search: string): CatalogService[] | null {
	const q = search.trim().toLowerCase();
	return q ? catalog.services.filter((s) => s.name.toLowerCase().includes(q)) : null;
}
