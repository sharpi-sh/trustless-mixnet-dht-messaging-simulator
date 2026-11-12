<script lang="ts">
  import { tick } from 'svelte';
  import type { LabNode, Snapshot } from './types';
  import NodeIcon from './NodeIcon.svelte';

  let {
    lab,
    selectedNode,
    selectedPath,
    onNode,
    onPath,
  }: {
    lab: Snapshot;
    selectedNode: string;
    selectedPath: string;
    onNode: (id: string) => void;
    onPath: (id: string) => void;
  } = $props();

  type Entry = {
    kind: 'node' | 'path';
    id: string;
    label: string;
    node?: LabNode;
  };
  const uid = $props.id();
  let field: HTMLInputElement;
  let open = $state(false);
  let query = $state('');
  let cursor = $state(0);
  let entries = $derived<Entry[]>([
    ...lab.topology.nodes.map((node) => ({
      kind: 'node' as const,
      id: node.id,
      label: node.label,
      node,
    })),
    ...lab.topology.paths.map((path) => ({
      kind: 'path' as const,
      id: path.id,
      label: path.source_id + ' ↔ ' + path.target_id,
    })),
  ]);
  let selected = $derived(
    entries.find((entry) =>
      entry.kind === 'node'
        ? selectedNode === entry.id
        : !selectedNode && selectedPath === entry.id,
    ),
  );
  let filtered = $derived.by(() => {
    const text = query.trim().toLowerCase();
    return text
      ? entries.filter((entry) =>
          (entry.label + ' ' + entry.id).toLowerCase().includes(text),
        )
      : entries;
  });
  function reveal() {
    if (open) return;
    open = true;
    query = '';
    cursor = Math.max(0, selected ? entries.indexOf(selected) : 0);
    scrollToCursor();
  }
  function scrollToCursor() {
    void tick().then(() =>
      document
        .getElementById(uid + '-option-' + cursor)
        ?.scrollIntoView({ block: 'nearest' }),
    );
  }
  function choose(entry: Entry) {
    if (entry.kind === 'node') onNode(entry.id);
    else onPath(entry.id);
    open = false;
  }
  function navigate(event: KeyboardEvent) {
    if (event.key === 'Escape' && open) {
      event.preventDefault();
      open = false;
    } else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      if (!open) reveal();
      else {
        cursor = Math.max(
          0,
          Math.min(
            filtered.length - 1,
            cursor + (event.key === 'ArrowDown' ? 1 : -1),
          ),
        );
        scrollToCursor();
      }
    } else if (event.key === 'Enter') {
      event.preventDefault();
      if (!open) reveal();
      else if (filtered[cursor]) choose(filtered[cursor]);
    }
  }
</script>

{#snippet icon(entry: Entry)}
  {#if entry.node}
    <NodeIcon node={entry.node} />
  {:else}
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      width="24"
      height="24"
      fill="none"
      stroke="currentColor"
      stroke-width="1.6"
    >
      <circle cx="4" cy="16" r="2.4" /><circle cx="20" cy="7" r="2.4" /><path
        d="M6.4 16h3c4.5 0 1-9 6-9h2.2"
      />
    </svg>
  {/if}
{/snippet}

<div class="picker">
  <label for={uid}>Inspect node or path</label>
  <div class="field">
    {#if selected}<span class="symbol">{@render icon(selected)}</span>{/if}
    <input
      id={uid}
      bind:this={field}
      role="combobox"
      type="text"
      autocomplete="off"
      aria-autocomplete="list"
      aria-expanded={open}
      aria-controls={uid + '-list'}
      aria-activedescendant={open && filtered[cursor]
        ? uid + '-option-' + cursor
        : undefined}
      placeholder={open ? 'Search nodes and paths' : 'Select a node or path'}
      value={open ? query : (selected?.label ?? '')}
      onfocus={reveal}
      onclick={reveal}
      onblur={() => (open = false)}
      oninput={(e) => {
        open = true;
        query = e.currentTarget.value;
        cursor = 0;
      }}
      onkeydown={navigate}
    />
    <svg
      class="chevron"
      aria-hidden="true"
      viewBox="0 0 12 12"
      fill="none"
      stroke="currentColor"><path d="m2 4 4 4 4-4" /></svg
    >
  </div>
  <div
    class="options"
    hidden={!open}
    id={uid + '-list'}
    role="listbox"
    aria-label="Nodes and paths"
  >
    {#if open}
      {#each filtered as entry, index (entry.kind + entry.id)}
        {#if index === 0 || filtered[index - 1].kind !== entry.kind}
          <div class="group-title" aria-hidden="true">
            {entry.kind === 'node' ? 'Nodes' : 'Paths'}
          </div>
        {/if}
        <button
          type="button"
          id={uid + '-option-' + index}
          role="option"
          tabindex="-1"
          data-inspect-id={entry.id}
          aria-selected={selected?.id === entry.id}
          class:active={index === cursor}
          onmousedown={(e) => e.preventDefault()}
          onclick={() => {
            field.focus();
            choose(entry);
          }}
        >
          {@render icon(entry)}<span>{entry.label}</span>
          {#if entry.node}<small>{entry.id}</small>{/if}
        </button>
      {:else}
        <div class="empty">No matching nodes or paths</div>
      {/each}
    {/if}
  </div>
</div>

<style>
  .picker {
    position: relative;
    min-width: 0;
  }
  label,
  .group-title {
    display: block;
    font-size: 0.8rem;
    font-weight: 650;
  }
  label {
    margin-bottom: 0.4rem;
  }
  .field {
    display: flex;
    align-items: center;
    position: relative;
  }
  .field input {
    width: 100%;
    padding-right: 2rem;
  }
  .symbol {
    position: absolute;
    left: 0.55rem;
    pointer-events: none;
  }
  .symbol + input {
    padding-left: 2.6rem;
  }
  .chevron {
    position: absolute;
    width: 0.8rem;
    height: 0.8rem;
    right: 0.8rem;
    pointer-events: none;
  }
  .options {
    position: absolute;
    z-index: 10;
    left: 0;
    right: 0;
    max-height: min(19rem, 45vh);
    overflow: auto;
    overscroll-behavior: contain;
    background: white;
    border: 1px solid var(--border);
    border-radius: 5px;
    box-shadow: 0 4px 14px #182d201a;
  }
  .group-title,
  .empty {
    padding: 0.5rem 0.7rem;
    color: var(--muted);
  }
  .group-title {
    background: var(--soft);
  }
  .options button {
    width: 100%;
    padding: 0.4rem 0.65rem;
    border: 0;
    border-radius: 0;
    display: flex;
    gap: 0.55rem;
    align-items: center;
    text-align: left;
  }
  .options button.active,
  .options button:hover {
    background: #e9f0e9;
  }
  .options button span {
    min-width: 0;
    overflow-wrap: anywhere;
  }
  small {
    margin-left: auto;
    font-family: var(--mono);
    color: var(--muted);
  }
</style>
