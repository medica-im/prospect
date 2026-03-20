<script lang="ts">
	import { page } from '$app/state';
	import { resolve } from '$app/paths';

	let { children } = $props();
</script>

<div class="max-w-6xl mx-auto w-full">
	<nav class="flex gap-4 border-b border-surface-500/30 mb-6 pb-2">
		<a
			href={resolve('/emails/send')}
			class="btn {page.url.pathname.includes('/emails/send') ? 'preset-filled-primary-500' : 'preset-outlined-surface-500'}"
		>
			Send Email
		</a>
		<a
			href={resolve('/emails/sent')}
			class="btn {page.url.pathname.includes('/emails/sent') ? 'preset-filled-primary-500' : 'preset-outlined-surface-500'}"
		>
			Sent Emails
		</a>
	</nav>

	{@render children()}
</div>
