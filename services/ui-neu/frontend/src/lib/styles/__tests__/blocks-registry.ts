// The block vocabulary contract: every block file and every class it must
// declare. Shared by blocks.test.ts (the file contract) and
// style-guide-drift.test.ts (the documentation contract).
export const BLOCKS: Record<string, string[]> = {
	panel: ['.panel', '.panel-title', '.panel-hint', '.panel-actions', '.panel-body', '.panel-section', '.panel-compact'],
	field: ['.field', '.field-label', '.field-help', '.field-error', '.field-row', '.field-control'],
	button: ['.btn', '.btn-primary', '.btn-danger', '.btn-warning', '.btn-ghost', '.btn-link', '.btn-icon', '.btn-sm'],
	chip: ['.chip', '.chip-danger', '.chip-warning', '.chip-success', '.chip-info', '.chip-sm'],
	badge: ['.badge', '.badge-status', '.badge-danger', '.badge-warning', '.badge-success', '.badge-info', '.badge-sm'],
	alert: ['.alert', '.alert-title', '.alert-body', '.alert-info', '.alert-warning', '.alert-danger', '.alert-success', '.alert-lg'],
	stat: ['.stat', '.stat-label', '.stat-value', '.stat-danger', '.stat-warning', '.stat-success', '.stat-info', '.stat-muted'],
	table: ['.table', '.table-header', '.table-row', '.table-cell', '.table-sort', '.table-compact'],
	'list-row': ['.list-row', '.list-row-lead', '.list-row-main', '.list-row-meta', '.list-row-actions', '.list-row-compact'],
	card: ['.card', '.card-header', '.card-title', '.card-body', '.card-footer', '.card-accent', '.card-status'],
	tabs: ['.tabs', '.tabs-tab', '.tabs-pills'],
	nav: ['.nav', '.nav-item', '.nav-badge', '.nav-logo'],
	toggle: ['.toggle', '.toggle-thumb', '.toggle-sm', '.toggle-lg'],
	progress: ['.progress', '.progress-track', '.progress-fill', '.progress-sm'],
	modal: ['.modal', '.modal-backdrop', '.modal-panel', '.modal-title', '.modal-body', '.modal-actions', '.modal-wide'],
	flyout: ['.flyout', '.flyout-item', '.flyout-divider'],
	'slide-over': ['.slide-over', '.slide-over-panel', '.slide-over-header'],
	skeleton: ['.skeleton', '.skeleton-text', '.skeleton-block', '.skeleton-card'],
	glyph: ['.glyph', '.glyph-sm', '.glyph-md', '.glyph-lg', '.glyph-danger', '.glyph-warning', '.glyph-success', '.glyph-info'],
	toast: ['.toast', '.toast-title', '.toast-body', '.toast-danger', '.toast-warning', '.toast-success', '.toast-info'],
	'status-dot': ['.status-dot'],
	'section-frame': ['.section-frame', '.section-frame-bar-top', '.section-frame-bar-bottom', '.section-frame-body'],
	'code-block': ['.code-block', '.code-block-scroll'],
	text: ['.eyebrow', '.mono', '.kbd']
};
