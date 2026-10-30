<script lang="ts">
	import { resolve } from '$app/paths';
	import { TONE_CLASS, deliveryLook } from './delivery';

	type SentEmail = {
		id: number;
		company_name: string;
		company_email: string;
		company_type: { id: number; name: string; label: string } | null;
		template_name: string | null;
		sent_at: string;
		success: boolean;
		mailgun_message_id: string;
		error_message: string;
		delivery_status: string;
		bounce_class: string;
		delivery_detail: string;
	};

	let {
		sentEmail,
		unsubscribed = false
	}: { sentEmail: SentEmail; unsubscribed?: boolean } = $props();

	let look = $derived(deliveryLook(sentEmail));
	let statusTitle = $derived(
		[look.explanation, sentEmail.delivery_detail, sentEmail.error_message]
			.filter(Boolean)
			.join('\n')
	);

	let formattedDate = $derived(
		new Date(sentEmail.sent_at).toLocaleDateString('fr-FR', {
			day: '2-digit',
			month: '2-digit',
			year: 'numeric',
			hour: '2-digit',
			minute: '2-digit',
			second: '2-digit'
		})
	);
</script>

<a
	href={resolve(`/emails/sent/${sentEmail.id}`)}
	class="card p-4 flex flex-col lg:grid lg:grid-cols-[140px_1fr_1fr_100px_170px] gap-2 lg:gap-4 items-center hover:preset-tonal-primary transition-colors no-underline"
>
	<span class="text-sm text-surface-600-400">{formattedDate}</span>
	<span class="font-medium truncate">{sentEmail.company_name}</span>
	<span class="text-sm truncate flex items-center gap-2">
		{sentEmail.company_email}
		{#if unsubscribed}
			<span class="badge preset-filled-error-500 text-xs whitespace-nowrap">Désabonné</span>
		{/if}
	</span>
	<span class="text-sm">
		{#if sentEmail.company_type}
			<span class="badge preset-filled-surface-500 text-xs">{sentEmail.company_type.label}</span>
		{/if}
	</span>
	<span>
		<span class="badge {TONE_CLASS[look.tone]} text-xs whitespace-nowrap" title={statusTitle}>
			{look.label}
		</span>
	</span>
</a>
