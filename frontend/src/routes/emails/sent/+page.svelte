<script lang="ts">
	import { resolve } from '$app/paths';
	import SentEmailCard from '$lib/emails/SentEmailCard.svelte';
	import {
		FILTER_OPTIONS,
		countByFilter,
		matchesFilter,
		type DeliveryFilter
	} from '$lib/emails/delivery';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	let search = $state('');
	let statusFilter = $state<DeliveryFilter>('');

	let unsubscribedSet = $derived(
		new Set((data.unsubscribed ?? []).map((e: string) => e.trim().toLowerCase()))
	);

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
		return result.filter((e: any) => matchesFilter(e, statusFilter));
	});

	let counts = $derived(countByFilter(data.sentEmails));
	let deadCount = $derived(counts.dead);
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
	<select class="select sm:w-64" bind:value={statusFilter}>
		{#each FILTER_OPTIONS as option (option.value)}
			<option value={option.value}>{option.label} ({counts[option.value]})</option>
		{/each}
	</select>
</div>

{#if counts.problem > 0}
	<div class="card preset-tonal-warning p-4 mb-6 flex flex-wrap items-center gap-3" role="status">
		<span class="flex-1 min-w-60">
			<strong>{counts.problem}</strong> email(s) à vérifier
			{#if deadCount > 0}
				dont <strong>{deadCount}</strong> à une adresse inexistante, à corriger dans le CRM.
			{/if}
		</span>
		<button type="button" class="btn preset-outlined-warning-500" onclick={() => (statusFilter = 'problem')}>
			Voir
		</button>
		<!-- A plain link: the browser downloads the file the proxy route streams back. -->
		<a class="btn preset-filled-primary-500" href={resolve('/emails/sent/problem-addresses.csv')} download>
			Télécharger les adresses à corriger (CSV)
		</a>
	</div>
{/if}

<!-- Column headers (desktop) -->
<div class="hidden lg:grid lg:grid-cols-[140px_1fr_1fr_100px_170px] gap-4 px-4 pb-2 text-sm font-bold text-surface-500">
	<span>Date</span>
	<span>Company</span>
	<span>Email</span>
	<span>Type</span>
	<span>Status</span>
</div>

<div class="space-y-2">
	{#each filtered as sentEmail (sentEmail.id)}
		<SentEmailCard
			{sentEmail}
			unsubscribed={unsubscribedSet.has(sentEmail.company_email.trim().toLowerCase())}
		/>
	{:else}
		<div class="card p-6 text-center text-surface-500">
			No sent emails found.
		</div>
	{/each}
</div>
