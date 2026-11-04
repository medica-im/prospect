<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { onMount } from 'svelte';

	let {
		success,
		message,
		skipped = 0,
		skippedEmails = [],
		scheduled = false
	}: {
		success: boolean;
		message: string;
		skipped?: number;
		skippedEmails?: string[];
		scheduled?: boolean;
	} = $props();

	let next = $derived(scheduled ? resolve('/emails/scheduled') : resolve('/emails/sent'));

	onMount(() => {
		// Skipped recipients are worth reading, so hold the page instead of
		// bouncing straight to the sent list.
		if (success && skipped === 0) {
			const timeout = setTimeout(() => {
				goto(next);
			}, 2000);
			return () => clearTimeout(timeout);
		}
	});
</script>

<div class="card p-8 text-center space-y-4">
	{#if success}
		<div class="text-6xl">&#10003;</div>
		<p class="text-lg font-bold text-success-500">{message}</p>

		{#if skipped > 0}
			<div class="card preset-tonal-warning p-4 text-left">
				<p class="font-bold">
					{skipped} destinataire(s) ignoré(s) — désabonné(s)
				</p>
				<ul class="mt-2 text-sm list-disc list-inside">
					{#each skippedEmails as email}
						<li>{email}</li>
					{/each}
				</ul>
			</div>
			<a href={next} class="btn preset-filled-primary-500 mt-2">
				{scheduled ? 'View scheduled batches' : 'View sent emails'}
			</a>
		{:else}
			<p class="text-sm text-surface-500">
				Redirecting to {scheduled ? 'scheduled batches' : 'sent emails'}...
			</p>
		{/if}
	{:else}
		<div class="text-6xl">&#10007;</div>
		<p class="text-lg font-bold text-error-500">{message}</p>
		<a href={resolve('/emails/send')} class="btn preset-filled-primary-500 mt-4">
			Try Again
		</a>
	{/if}
</div>
