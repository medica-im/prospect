<script lang="ts">
	import CompanyTable from '$lib/emails/CompanyTable.svelte';
	import type { SelectedRecipient } from '$lib/emails/CompanyTable.svelte';
	import TemplateSelector from '$lib/emails/TemplateSelector.svelte';
	import SendConfirmation from '$lib/emails/SendConfirmation.svelte';
	import type { PageData } from './$types';
	import { sendEmails } from './send.remote.ts';

	let { data }: { data: PageData } = $props();

	let currentStep = $state(0);
	let selectedRecipients = $state<SelectedRecipient[]>([]);
	let selectedTemplate = $state<any>(null);

	let selectedCompanyTypes = $derived(
		new Set(selectedRecipients.map((r) => r.company_type))
	);

	let recipientsJson = $derived(
		JSON.stringify(
			selectedRecipients.map((r) => ({
				company_name: r.company_name,
				company_email: r.company_email,
				company_type_id: selectedTemplate?.company_type?.id ?? 0,
				twenty_crm_id: r.company_id
			}))
		)
	);

	let formResult = $derived(sendEmails.result);
</script>

<svelte:head>
	<title>Send Email</title>
</svelte:head>

<h1 class="h3 mb-6">Send Prospect Email</h1>

<!-- Step indicators -->
<div class="flex gap-2 mb-8">
	{#each ['Select Companies', 'Choose Template', 'Confirmation'] as label, i}
		<div class="flex items-center gap-2">
			<span
				class="badge-icon {i <= currentStep ? 'preset-filled-primary-500' : 'preset-filled-surface-500'}"
			>
				{i + 1}
			</span>
			<span class="text-sm {i === currentStep ? 'font-bold' : 'text-surface-500'}">{label}</span>
			{#if i < 2}
				<span class="text-surface-400 mx-1">→</span>
			{/if}
		</div>
	{/each}
</div>

{#if currentStep === 0}
	<!-- Step 0: Select companies and emails -->
	<div class="flex justify-end mb-4">
		<button
			class="btn preset-filled-primary-500"
			disabled={selectedRecipients.length === 0}
			onclick={() => (currentStep = 1)}
		>
			Next: Choose Template →
		</button>
	</div>

	<CompanyTable
		companies={data.companies}
		companyTypes={data.companyTypes}
		twentyBaseUrl={data.twentyBaseUrl}
		emailStats={data.emailStats}
		bind:selectedRecipients
	/>

{:else if currentStep === 1}
	<!-- Step 1: Select template -->
	<TemplateSelector
		templates={data.templates}
		{selectedCompanyTypes}
		bind:selectedTemplate
	/>

	<form
		{...sendEmails.enhance(async ({ submit }) => {
			try {
				await submit();
				if (sendEmails.result?.success) {
					currentStep = 2;
				}
			} catch (error) {
				console.error(error);
			}
		})}
		class="mt-6 flex justify-between"
	>
		<button
			type="button"
			class="btn preset-outlined-surface-500"
			onclick={() => (currentStep = 0)}
		>
			← Back
		</button>

		<input type="hidden" name="template_id" value={selectedTemplate?.id ?? ''} />
		<input type="hidden" name="recipients" value={recipientsJson} />

		<button
			type="submit"
			class="btn preset-filled-primary-500"
			disabled={!selectedTemplate || !!sendEmails.pending}
		>
			{#if sendEmails.pending}
				Sending...
			{:else}
				Send {selectedRecipients.length} Email(s)
			{/if}
		</button>
	</form>

{:else if currentStep === 2}
	<!-- Step 2: Confirmation -->
	<SendConfirmation
		success={formResult?.success ?? false}
		message={formResult?.message ?? 'Unknown error'}
	/>
{/if}
