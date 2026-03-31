<script lang="ts">
	import { enhance } from '$app/forms';
	import type { ActionData } from './$types';

	let { form }: { form: ActionData } = $props();
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

		<form method="POST" use:enhance class="space-y-4">
			<label class="label">
				<span>Username</span>
				<input type="text" name="username" class="input" required autocomplete="username" />
			</label>

			<label class="label">
				<span>Password</span>
				<input type="password" name="password" class="input" required autocomplete="current-password" />
			</label>

			<button type="submit" class="btn preset-filled-primary-500 w-full">
				Log in
			</button>
		</form>
	</div>
</div>
