<script lang="ts">
	import SentEmailCard from '$lib/emails/SentEmailCard.svelte';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	let search = $state('');
	let statusFilter = $state('');

	let filtered = $derived.by(() => {
		let result = data.sentEmails;
		if (search) {
			const q = search.toLowerCase();
			result = result.filter(
				(e: any) =>
					e.company_name.toLowerCase().includes(q) ||
					e.company_email.toLowerCase().includes(q)
			);
		}
		if (statusFilter === 'success') {
			result = result.filter((e: any) => e.success);
		} else if (statusFilter === 'failed') {
			result = result.filter((e: any) => !e.success);
		}
		return result;
	});
</script>

<svelte:head>
	<title>Sent Emails</title>
</svelte:head>

<div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mb-6">
	<h1 class="h3">Sent Emails ({data.sentEmails.length})</h1>
</div>

<div class="flex flex-col sm:flex-row gap-3 mb-6">
	<input
		type="search"
		placeholder="Search by company or email..."
		class="input flex-1"
		bind:value={search}
	/>
	<select class="select w-40" bind:value={statusFilter}>
		<option value="">All status</option>
		<option value="success">Sent</option>
		<option value="failed">Failed</option>
	</select>
</div>

<!-- Column headers (desktop) -->
<div class="hidden lg:grid lg:grid-cols-[140px_1fr_1fr_100px_80px] gap-4 px-4 pb-2 text-sm font-bold text-surface-500">
	<span>Date</span>
	<span>Company</span>
	<span>Email</span>
	<span>Type</span>
	<span>Status</span>
</div>

<div class="space-y-2">
	{#each filtered as sentEmail (sentEmail.id)}
		<SentEmailCard {sentEmail} />
	{:else}
		<div class="card p-6 text-center text-surface-500">
			No sent emails found.
		</div>
	{/each}
</div>
