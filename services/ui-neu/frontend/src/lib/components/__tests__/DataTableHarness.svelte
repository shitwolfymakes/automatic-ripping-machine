<script lang="ts">
	import DataTable from '../DataTable.svelte';
	import type { TableColumn } from '../dataTable';

	interface Row {
		id: string;
		name: string;
		count: number;
	}
	interface Props {
		rows: Row[];
		activeKey?: string | null;
		empty?: string;
		columns?: TableColumn<Row>[];
	}

	const defaultColumns: TableColumn<Row>[] = [
		{ id: 'name', header: 'Name', cell: (r) => ({ text: r.name }) },
		{ id: 'count', header: 'Count', align: 'end', cell: (r) => ({ text: String(r.count) }) }
	];

	let { rows, activeKey = null, empty, columns = defaultColumns }: Props = $props();
</script>

<DataTable {columns} {rows} rowKey={(r) => r.id} {activeKey} label="Things" {empty}>
	{#snippet actions(row)}
		<button type="button">Open {row.name}</button>
	{/snippet}
</DataTable>
