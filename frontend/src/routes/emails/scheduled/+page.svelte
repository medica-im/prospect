<script lang="ts">
	import { invalidateAll } from '$app/navigation';
	import type { PageData } from './$types';
	import { cancelBatch } from './scheduled.remote.ts';

	let { data }: { data: PageData } = $props();

	const STATUS_LABEL: Record<string, string> = {
		pending: 'Waiting',
		running: 'Queuing',
		done: 'Queued',
		cancelled: 'Cancelled'
	};

	// Shown in the zone the operator chose, since that is the one they reasoned in.
	function when(batch: { scheduled_at: string; timezone: string }) {
		return new Date(batch.scheduled_at).toLocaleString('fr-FR', {
			dateStyle: 'medium',
			timeStyle: 'short',
			timeZone: batch.timezone
		});
	}
</script>

<svelte:head>
	<title>Scheduled Emails</title>
</svelte:head>

<h1 class="h3 mb-6">Scheduled batches</h1>

{#if data.batches.length === 0}
	<p class="text-surface-600-400">Nothing scheduled.</p>
{:else}
	<div class="table-wrap">
		<table class="table">
			<thead>
				<tr>
					<th>When</th>
					<th>Zone</th>
					<th>Template</th>
					<th>Recipients</th>
					<th>Status</th>
					<th></th>
				</tr>
			</thead>
			<tbody>
				{#each data.batches as batch (batch.id)}
					<tr>
						<td>{when(batch)}</td>
						<td>{batch.timezone}</td>
						<td>{batch.template_name ?? '(template deleted)'}</td>
						<td>
							{batch.recipient_count}
							{#if batch.status === 'done'}
								<span class="text-sm text-surface-600-400">
									({batch.queued} queued, {batch.skipped} skipped)
								</span>
							{/if}
						</td>
						<td>{STATUS_LABEL[batch.status] ?? batch.status}</td>
						<td class="text-right">
							{#if batch.status === 'pending'}
								<form
									{...cancelBatch.enhance(async ({ submit }) => {
										await submit();
										await invalidateAll();
									})}
								>
									<input type="hidden" name="id" value={batch.id} />
									<button type="submit" class="btn btn-sm preset-outlined-error-500">
										Cancel
									</button>
								</form>
							{/if}
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
{/if}
