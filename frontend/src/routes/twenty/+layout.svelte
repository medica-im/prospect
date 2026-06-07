<script lang="ts">
	import { page } from '$app/state';
	import { resolve } from '$app/paths';

	let { children } = $props();
</script>

<div class="max-w-6xl mx-auto w-full">
	<nav class="flex gap-4 border-b border-surface-500/30 mb-6 pb-2">
		<a
			href={resolve('/twenty/import')}
			class="btn {page.url.pathname.includes('/twenty/import') ? 'preset-filled-primary-500' : 'preset-outlined-surface-500'}"
		>
			Import Companies
		</a>
	</nav>

	{@render children()}
</div>
