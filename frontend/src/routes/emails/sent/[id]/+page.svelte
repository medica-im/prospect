<script lang="ts">
	import { resolve } from '$app/paths';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();
</script>

<svelte:head>
	<title>{data.preview.subject}</title>
</svelte:head>

<div class="space-y-6">
	<a href={resolve('/emails/sent')} class="btn preset-outlined-surface-500">
		← Back to Sent Emails
	</a>

	<div class="card p-6 space-y-4">
		<h1 class="h3">{data.preview.subject}</h1>

		<div class="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
			<span class="font-bold text-surface-500">Date</span>
			<span>{new Date(data.preview.sent_at).toLocaleString()}</span>
			<span class="font-bold text-surface-500">From</span>
			<span>{data.preview.from_email}</span>
			<span class="font-bold text-surface-500">To</span>
			<span>{data.preview.to_email}</span>
			<span class="font-bold text-surface-500">Message ID</span>
			<span class="break-all">{data.preview.mailgun_message_id}</span>
		</div>

		<div class="border-t border-surface-500/30 pt-4">
			<iframe
				title="Email preview"
				srcdoc={data.preview.html_body}
				sandbox=""
				class="w-full min-h-[600px] bg-white rounded border border-surface-300"
			></iframe>
		</div>
	</div>
</div>
