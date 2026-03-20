<script lang="ts">
	import { resolve } from '$app/paths';

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
	};

	let { sentEmail }: { sentEmail: SentEmail } = $props();

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
	class="card p-4 flex flex-col lg:grid lg:grid-cols-[140px_1fr_1fr_100px_80px] gap-2 lg:gap-4 items-center hover:preset-tonal-primary transition-colors no-underline"
>
	<span class="text-sm text-surface-600">{formattedDate}</span>
	<span class="font-medium truncate">{sentEmail.company_name}</span>
	<span class="text-sm truncate">{sentEmail.company_email}</span>
	<span class="text-sm">
		{#if sentEmail.company_type}
			<span class="badge preset-filled-surface-500 text-xs">{sentEmail.company_type.label}</span>
		{/if}
	</span>
	<span>
		{#if sentEmail.success}
			<span class="badge preset-filled-success-500 text-xs">Sent</span>
		{:else}
			<span class="badge preset-filled-error-500 text-xs">Failed</span>
		{/if}
	</span>
</a>
