<script lang="ts">
  import type { Snippet } from 'svelte'

  interface Props {
    title: string
    size: number
    children: Snippet
  }
  let { title, size, children }: Props = $props()

  let list: HTMLOListElement
  let following = true // false while the reader has scrolled up

  $effect(() => {
    void size
    if (list.scrollHeight - list.clientHeight <= 40) following = true
    if (following) list.scrollTop = list.scrollHeight
  })
</script>

<section>
  <h2>{title}</h2>
  <ol bind:this={list} onscroll={() => (following = list.scrollTop + list.clientHeight >= list.scrollHeight - 40)}>
    {@render children()}
  </ol>
</section>

<style>
  section {
    display: grid;
    grid-template-rows: auto minmax(0, 1fr);
    min-height: 0;
  }

  h2 {
    margin: 0 0 0.25rem;
    font-size: 13px;
    font-weight: 700;
    font-variant: small-caps;
    letter-spacing: 0.06em;
  }

  ol {
    list-style: none;
    margin: 0;
    padding: 0;
    overflow-y: auto;
    scrollbar-width: thin;
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    gap: 0.35rem;
    align-content: start;
    font-size: 13px;
  }

  @media (max-width: 800px), (max-height: 500px) {
    ol {
      max-height: 40vh;
    }
  }
</style>
