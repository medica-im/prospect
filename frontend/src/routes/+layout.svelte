<script lang="ts">
	import { page } from '$app/state';
	import { locales, localizeHref } from '$lib/paraglide/runtime';
	import Header from './Header.svelte';
	import './layout.css';

	let { children } = $props();
</script>

<div class="app">
	<Header />
	<main>{@render children()}</main>
</div>

<div style="display:none">
	{#each locales as locale}
		<a href={localizeHref(page.url.pathname, { locale })}>{locale}</a>
	{/each}
</div>

<style>
	.app {
		display: flex;
		flex-direction: column;
		min-height: 100vh;
	}

	main {
		flex: 1;
		display: flex;
		flex-direction: column;
		padding: 1rem;
		width: 100%;
		max-width: 64rem;
		margin: 0 auto;
		box-sizing: border-box;
	}

	/* On large screens, let pages use the full viewport width. Individual
	   pages/layouts still cap their own content (e.g. text pages) as needed. */
	@media (min-width: 1280px) {
		main {
			max-width: none;
		}
	}
</style>
