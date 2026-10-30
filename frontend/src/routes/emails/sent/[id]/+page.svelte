<script lang="ts">
	import { resolve } from '$app/paths';
	import { TONE_CLASS, deliveryLook, eventLabel } from '$lib/emails/delivery';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	let look = $derived(deliveryLook(data.preview));
	const formatTime = (iso: string) =>
		new Date(iso).toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'medium' });
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

		<div class="border-t border-surface-500/30 pt-4 space-y-3" aria-labelledby="delivery-title">
			<h2 id="delivery-title" class="h5">Distribution</h2>
			<p class="flex flex-wrap items-center gap-2">
				<span class="badge {TONE_CLASS[look.tone]}">{look.label}</span>
				{#if data.preview.delivery_updated_at}
					<span class="text-sm text-surface-500">
						{formatTime(data.preview.delivery_updated_at)}
					</span>
				{/if}
			</p>
			<p class="text-sm">{look.explanation}</p>
			{#if data.preview.delivery_detail}
				<p class="text-sm">
					<span class="font-bold text-surface-500">Réponse du serveur</span>
					<code class="block mt-1 p-2 rounded bg-surface-100-900 break-all whitespace-pre-wrap">
						{data.preview.delivery_detail}
					</code>
				</p>
			{/if}
			{#if data.preview.error_message}
				<p class="text-sm">
					<span class="font-bold text-surface-500">Erreur d'envoi</span>
					<code class="block mt-1 p-2 rounded bg-surface-100-900 break-all whitespace-pre-wrap">
						{data.preview.error_message}
					</code>
				</p>
			{/if}
			{#if data.preview.events.length > 0}
				<ol class="text-sm space-y-1">
					{#each data.preview.events as event, i (i)}
						<li class="grid grid-cols-[auto_1fr] gap-x-3">
							<span class="text-surface-500 tabular-nums">{formatTime(event.occurred_at)}</span>
							<span>
								{eventLabel(event.kind, event.severity)}
								{#if event.enhanced_code || event.smtp_code}
									<span class="text-surface-500">
										({[event.smtp_code, event.enhanced_code].filter(Boolean).join(' ')})
									</span>
								{/if}
							</span>
						</li>
					{/each}
				</ol>
			{:else if data.preview.success}
				<p class="text-sm text-surface-500">Aucun retour du serveur du destinataire pour le moment.</p>
			{/if}
		</div>

		<div class="border-t border-surface-500/30 pt-4">
			<iframe
				title="Email preview"
				srcdoc={data.preview.html_body}
				sandbox=""
				class="w-full min-h-[600px] bg-white rounded border border-surface-300-700"
			></iframe>
		</div>
	</div>
</div>
