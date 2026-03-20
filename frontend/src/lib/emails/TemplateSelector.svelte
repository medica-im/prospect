<script lang="ts">
	type CompanyType = {
		id: number;
		name: string;
		label: string;
	};

	type Template = {
		id: number;
		name: string;
		subject_template: string;
		company_type: CompanyType;
	};

	let {
		templates,
		selectedCompanyTypes,
		selectedTemplate = $bindable(null)
	}: {
		templates: Template[];
		selectedCompanyTypes: Set<string>;
		selectedTemplate: Template | null;
	} = $props();

	let available = $derived(
		templates.filter((t) => selectedCompanyTypes.has(t.company_type.name))
	);
</script>

<div class="space-y-4">
	{#if available.length === 0}
		<div class="card p-6 text-center text-surface-500">
			No templates available for the selected company types.
		</div>
	{:else}
		<div class="grid gap-4 sm:grid-cols-2">
			{#each available as template (template.id)}
				<button
					type="button"
					class="card p-4 text-left transition-all {selectedTemplate?.id === template.id
						? 'preset-outlined-primary-500 ring-2 ring-primary-500'
						: 'preset-outlined-surface-500 hover:preset-tonal-surface'}"
					onclick={() => (selectedTemplate = template)}
				>
					<div class="flex items-center justify-between mb-2">
						<h3 class="font-bold">{template.name}</h3>
						<span class="badge preset-filled-surface-500 text-xs">
							{template.company_type.label}
						</span>
					</div>
					<p class="text-sm text-surface-600">
						Subject: {template.subject_template}
					</p>
				</button>
			{/each}
		</div>
	{/if}
</div>
