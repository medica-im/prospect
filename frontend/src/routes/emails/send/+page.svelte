<script lang="ts">
	import { dev } from '$app/environment';
	import { invalidateAll, pushState, replaceState } from '$app/navigation';
	import { page } from '$app/state';
	import { tick } from 'svelte';
	import CompanyTable from '$lib/emails/CompanyTable.svelte';
	import type { SelectedRecipient } from '$lib/emails/selection';
	import TemplateSelector from '$lib/emails/TemplateSelector.svelte';
	import SendConfirmation from '$lib/emails/SendConfirmation.svelte';
	import { JsonView } from '@zerodevx/svelte-json-view';
	import type { PageData } from './$types';
	import { sendEmails } from './send.remote.ts';

	let { data }: { data: PageData } = $props();

	// The steps are shallow history entries: Next pushes one, so the browser's
	// Back returns to the selection without a reload or a refetch. A reload
	// drops page.state and lands on the first step, which is what we want since
	// the selection only lives in memory.
	let currentStep = $derived(page.state.step ?? 0);
	let table: ReturnType<typeof CompanyTable> | undefined = $state();

	let selectionScrollY = 0;
	async function toTemplateStep() {
		selectionScrollY = window.scrollY;
		pushState('', { step: 1 });
		await tick();
		window.scrollTo(0, 0);
	}

	// Through history, so the in-page Back and the browser's agree.
	function backToSelection() {
		history.back();
	}

	$effect(() => {
		if (currentStep === 0 && selectionScrollY) {
			const y = selectionScrollY;
			tick().then(() => window.scrollTo(0, y));
		}
	});

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
				company_type_id: data.companyTypes.find((ct: { id: number; name: string }) => ct.name === r.company_type)?.id ?? 0,
				twenty_crm_id: r.company_id
			}))
		)
	);

	let formResult = $derived(sendEmails.result);

	// The page data is fetched once per visit (Twenty is slow); this re-runs the
	// load on demand. The selection survives, it lives in this component.
	let refreshing = $state(false);
	async function refreshData() {
		refreshing = true;
		try {
			await invalidateAll();
		} finally {
			refreshing = false;
		}
	}

	let debugOpen = $state(false);
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

{#if dev}
	<details class="mb-6" bind:open={debugOpen}>
		<summary class="h4 cursor-pointer">Debug: data</summary>
		<!-- Rendering the whole dataset is slow; only do it when asked. -->
		{#if debugOpen}
			<JsonView json={data} />
		{/if}
	</details>
{/if}

<!-- Step 0 stays mounted while hidden, so filters, select mode and the
     selection are all still there when coming back. -->
<div hidden={currentStep !== 0}>
	<div class="flex items-center justify-end gap-3 mb-4">
		<span class="text-sm text-surface-600-400">
			Data from {new Date(data.loadedAt).toLocaleTimeString('fr-FR', {
				hour: '2-digit',
				minute: '2-digit',
				second: '2-digit'
			})}
		</span>
		<button
			type="button"
			class="btn preset-outlined-surface-500"
			disabled={refreshing}
			onclick={refreshData}
		>
			{refreshing ? 'Refreshing…' : '↻ Refresh data'}
		</button>
		<button
			class="btn preset-filled-primary-500"
			disabled={selectedRecipients.length === 0}
			onclick={toTemplateStep}
		>
			Next: Choose Template →
		</button>
	</div>

	<CompanyTable
		bind:this={table}
		companies={data.companies}
		companyTypes={data.companyTypes}
		twentyBaseUrl={data.twentyBaseUrl}
		addressStats={data.addressStats}
		unsubscribed={data.unsubscribed}
		bind:selectedRecipients
	/>
</div>

{#if currentStep === 1}
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
					// Replacing the template step means Back from the confirmation
					// returns to the selection, emptied so nothing goes out twice.
					table?.clearSelection();
					replaceState('', { step: 2 });
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
			onclick={backToSelection}
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
		skipped={formResult?.skipped ?? 0}
		skippedEmails={formResult?.skippedEmails ?? []}
	/>
{/if}
