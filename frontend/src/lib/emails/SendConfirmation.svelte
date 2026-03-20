<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { onMount } from 'svelte';

	let {
		success,
		message
	}: {
		success: boolean;
		message: string;
	} = $props();

	onMount(() => {
		if (success) {
			const timeout = setTimeout(() => {
				goto(resolve('/emails/sent'));
			}, 2000);
			return () => clearTimeout(timeout);
		}
	});
</script>

<div class="card p-8 text-center space-y-4">
	{#if success}
		<div class="text-6xl">&#10003;</div>
		<p class="text-lg font-bold text-success-500">{message}</p>
		<p class="text-sm text-surface-500">Redirecting to sent emails...</p>
	{:else}
		<div class="text-6xl">&#10007;</div>
		<p class="text-lg font-bold text-error-500">{message}</p>
		<a href={resolve('/emails/send')} class="btn preset-filled-primary-500 mt-4">
			Try Again
		</a>
	{/if}
</div>
