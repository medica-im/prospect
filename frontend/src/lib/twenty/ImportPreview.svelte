<script lang="ts">
	import { onMount } from 'svelte';

	type PreviewRow = {
		name: string;
		email: string;
		postcode: string;
		domain: string;
	};

	let {
		uploadId,
		transformerId,
		previewRows = $bindable([]),
		totalDeduplicated = $bindable(0),
		onConfirm,
		onBack
	}: {
		uploadId: string;
		transformerId: number | null;
		previewRows: PreviewRow[];
		totalDeduplicated: number;
		onConfirm: () => void;
		onBack: () => void;
	} = $props();

	let loading = $state(true);
	let error = $state('');

	onMount(async () => {
		try {
			const response = await fetch('/twenty/import/api/preview', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					upload_id: uploadId,
					transformer_id: transformerId
				})
			});
			const json = await response.json();
			if (response.ok) {
				previewRows = json.rows;
				totalDeduplicated = json.total_deduplicated;
			} else {
				error = json.detail || 'Preview failed';
			}
		} catch (e) {
			error = String(e);
		} finally {
			loading = false;
		}
	});
</script>

<div class="space-y-6">
	{#if loading}
		<p class="text-surface-500">Loading preview...</p>
	{:else if error}
		<aside class="alert preset-filled-error-500">
			<p>{error}</p>
		</aside>
	{:else}
		<div class="card p-4">
			<p class="font-bold mb-2">
				{totalDeduplicated} unique companies found (after deduplication)
			</p>
			<p class="text-sm text-surface-500 mb-4">Preview of 3 random entries:</p>

			<div class="table-container">
				<table class="table">
					<thead>
						<tr>
							<th>Name</th>
							<th>Email</th>
							<th>Postal Code</th>
							<th>Domain</th>
						</tr>
					</thead>
					<tbody>
						{#each previewRows as row}
							<tr>
								<td>{row.name}</td>
								<td>{row.email}</td>
								<td>{row.postcode}</td>
								<td>{row.domain || '—'}</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		</div>
	{/if}

	<div class="flex justify-between">
		<button class="btn preset-outlined-surface-500" onclick={onBack}>← Back</button>
		<button
			class="btn preset-filled-primary-500"
			disabled={loading || !!error}
			onclick={onConfirm}
		>
			Import {totalDeduplicated} Companies →
		</button>
	</div>
</div>
