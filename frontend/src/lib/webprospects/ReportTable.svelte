<script lang="ts">
	import { ExternalLinkIcon } from '@lucide/svelte';

	export type ReportRow = {
		name: string;
		status: string;
		twenty_company_id?: string;
		missing_fields?: string[];
		error?: string;
		duplicate_company_id?: string;
		duplicate_company_name?: string;
	};

	let {
		rows,
		title = 'Report',
		twentyBaseUrl = ''
	}: { rows: ReportRow[]; title?: string; twentyBaseUrl?: string } = $props();

	function statusBadge(status: string): string {
		if (status === 'created') return 'preset-filled-success-500';
		if (status === 'updated') return 'preset-filled-primary-500';
		if (status === 'already_present') return 'preset-filled-warning-500';
		if (status === 'skipped') return 'preset-tonal';
		return 'preset-filled-error-500';
	}

	function statusLabel(status: string): string {
		if (status === 'already_present') return 'already in Twenty';
		return status;
	}
</script>

{#if rows.length > 0}
	<div class="space-y-2">
		<h3 class="h4">{title}</h3>
		<div class="table-container">
			<table class="table">
				<thead>
					<tr>
						<th>MSP</th>
						<th>Status</th>
						<th>Fields</th>
						<th>Duplicate of</th>
						<th>Details</th>
					</tr>
				</thead>
				<tbody>
					{#each rows as row (row.name + row.status)}
						<tr>
							<td>{row.name || '—'}</td>
							<td>
								<span class="badge {statusBadge(row.status)} text-xs">
									{statusLabel(row.status)}
								</span>
							</td>
							<td class="text-sm text-surface-500">
								{row.missing_fields && row.missing_fields.length
									? row.missing_fields.join(', ')
									: '—'}
							</td>
							<td class="text-sm">
								{#if row.duplicate_company_name}
									{#if twentyBaseUrl && row.duplicate_company_id}
										<a
											class="anchor inline-flex items-center gap-1"
											href="{twentyBaseUrl}/object/company/{row.duplicate_company_id}"
											target="_blank"
											rel="noopener noreferrer"
										>
											{row.duplicate_company_name}
											<ExternalLinkIcon class="size-3.5 shrink-0" />
										</a>
									{:else}
										{row.duplicate_company_name}
									{/if}
								{:else}
									<span class="text-surface-500">—</span>
								{/if}
							</td>
							<td class="text-sm text-surface-500">{row.error || '—'}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	</div>
{/if}
