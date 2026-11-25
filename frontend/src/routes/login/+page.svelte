<script lang="ts">
	import { enhance } from '$app/forms';
	import { LoaderCircleIcon } from '@lucide/svelte';
	import type { ActionData } from './$types';

	let { form }: { form: ActionData } = $props();

	// Logging in waits on Django (password hashing, lockout check), so show that
	// something is happening and refuse a second click.
	let submitting = $state(false);
</script>

<svelte:head>
	<title>Login</title>
</svelte:head>

<div class="flex items-center justify-center min-h-[60vh]">
	<div class="card p-8 w-full max-w-sm space-y-6">
		<h1 class="h3 text-center">Prospect</h1>

		{#if form?.error}
			<div class="p-3 preset-tonal-error-500 rounded text-sm">
				{form.error}
			</div>
		{/if}

		<form
			method="POST"
			class="space-y-4"
			use:enhance={() => {
				submitting = true;
				return async ({ update }) => {
					await update();
					submitting = false;
				};
			}}
		>
			<label class="label">
				<span>Username</span>
				<input type="text" name="username" class="input" required autocomplete="username" />
			</label>

			<label class="label">
				<span>Password</span>
				<input type="password" name="password" class="input" required autocomplete="current-password" />
			</label>

			<button
				type="submit"
				class="btn preset-filled-primary-500 w-full"
				disabled={submitting}
				aria-busy={submitting}
			>
				{#if submitting}
					<LoaderCircleIcon class="size-4 animate-spin" aria-hidden="true" />
					Logging in…
				{:else}
					Log in
				{/if}
			</button>
		</form>
	</div>
</div>
