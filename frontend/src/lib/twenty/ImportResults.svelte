<script lang="ts">
	import { onMount, onDestroy } from 'svelte';

	type ResultRow = {
		name: string;
		status: string;
		error?: string;
	};

	let {
		uploadId,
		transformerId,
		selectedCompanyTypeId,
		totalDeduplicated,
		importResults = $bindable(null),
		onReset
	}: {
		uploadId: string;
		transformerId: number | null;
		selectedCompanyTypeId: number | null;
		totalDeduplicated: number;
		importResults: any;
		onReset: () => void;
	} = $props();

	let loading = $state(true);
	let error = $state('');
	let details = $state<ResultRow[]>([]);
	let taskId = $state('');
	let progress = $state({ processed: 0, total: 0, created: 0, skipped: 0, failed: 0 });
	let pollTimer: ReturnType<typeof setInterval> | null = null;

	let progressPercent = $derived(
		progress.total > 0 ? Math.round((progress.processed / progress.total) * 100) : 0
	);

	onMount(async () => {
		try {
			const response = await fetch('/twenty/import/api/import', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					upload_id: uploadId,
					transformer_id: transformerId,
					company_type_id: selectedCompanyTypeId
				})
			});
			const json = await response.json();

			if (!response.ok) {
				error = json.detail || 'Failed to start import';
				loading = false;
				return;
			}

			taskId = json.task_id;
			pollTimer = setInterval(pollStatus, 2000);
		} catch (e) {
			error = String(e);
			loading = false;
		}
	});

	onDestroy(() => {
		if (pollTimer) clearInterval(pollTimer);
	});

	async function pollStatus() {
		if (!taskId) return;

		try {
			const response = await fetch(
				`/twenty/import/api/import-status?task_id=${encodeURIComponent(taskId)}`
			);
			const json = await response.json();

			if (json.state === 'PROGRESS') {
				progress = {
					processed: json.processed,
					total: json.total,
					created: json.created,
					skipped: json.skipped,
					failed: json.failed
				};
			} else if (json.state === 'SUCCESS') {
				if (pollTimer) clearInterval(pollTimer);
				importResults = {
					created: json.created,
					skipped: json.skipped,
					failed: json.failed,
					details: json.details
				};
				details = json.details || [];
				loading = false;
			} else if (json.state === 'FAILED') {
				if (pollTimer) clearInterval(pollTimer);
				error = json.error || 'Import failed';
				loading = false;
			}
		} catch (e) {
			console.error('Poll error:', e);
		}
	}

	function statusBadge(status: string): string {
		if (status === 'created') return 'preset-filled-success-500';
		if (status === 'skipped') return 'preset-filled-warning-500';
		return 'preset-filled-error-500';
	}
</script>

<div class="space-y-6">
	{#if loading}
		<div class="card p-6 text-center space-y-4">
			<p class="text-lg font-bold mb-2">Importing companies to Twenty CRM...</p>

			{#if progress.total > 0}
				<div class="w-full bg-surface-200 rounded-full h-4 overflow-hidden">
					<div
						class="bg-primary-500 h-4 rounded-full transition-all duration-300"
						style="width: {progressPercent}%"
					></div>
				</div>
				<p class="text-sm text-surface-500">
					{progress.processed} / {progress.total} companies processed ({progressPercent}%)
				</p>
				<div class="flex justify-center gap-6 text-sm">
					<span class="text-green-600">{progress.created} created</span>
					<span class="text-yellow-600">{progress.skipped} skipped</span>
					<span class="text-red-600">{progress.failed} failed</span>
				</div>
			{:else}
				<p class="text-surface-500">Starting import task...</p>
			{/if}
		</div>
	{:else if error}
		<aside class="alert preset-filled-error-500">
			<p>{error}</p>
		</aside>
	{:else if importResults}
		<div class="card p-6 space-y-4">
			<h3 class="h4">Import Complete</h3>

			<div class="grid grid-cols-3 gap-4">
				<div class="card p-4 text-center">
					<p class="text-2xl font-bold text-green-600">{importResults.created}</p>
					<p class="text-sm text-surface-500">Created</p>
				</div>
				<div class="card p-4 text-center">
					<p class="text-2xl font-bold text-yellow-600">{importResults.skipped}</p>
					<p class="text-sm text-surface-500">Skipped</p>
				</div>
				<div class="card p-4 text-center">
					<p class="text-2xl font-bold text-red-600">{importResults.failed}</p>
					<p class="text-sm text-surface-500">Failed</p>
				</div>
			</div>
		</div>

		{#if details.length > 0}
			<div class="table-container">
				<table class="table">
					<thead>
						<tr>
							<th>Company</th>
							<th>Status</th>
							<th>Error</th>
						</tr>
					</thead>
					<tbody>
						{#each details as row}
							<tr>
								<td>{row.name}</td>
								<td>
									<span class="badge {statusBadge(row.status)} text-xs">
										{row.status}
									</span>
								</td>
								<td class="text-sm text-surface-500">{row.error || '—'}</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		{/if}

		<button class="btn preset-filled-primary-500" onclick={onReset}>
			New Import
		</button>
	{/if}
</div>
