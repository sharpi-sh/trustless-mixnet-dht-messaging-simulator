<script lang="ts">
  let { label, text, uid }: { label: string; text: string; uid: string } =
    $props();
  const tipId = $derived(`field-help-${uid}`);
</script>

<button
  type="button"
  class="help"
  aria-label={`Information about ${label}`}
  aria-describedby={tipId}
  title={text}
  onclick={(event) => {
    event.preventDefault();
    event.stopPropagation();
  }}>i<span class="tip" id={tipId} role="tooltip">{text}</span></button
>

<style>
  .help {
    position: relative;
    display: inline-grid;
    place-items: center;
    width: 0.9rem;
    height: 0.9rem;
    margin-left: 0.3rem;
    padding: 0;
    border: 1px solid #77888f;
    border-radius: 50%;
    color: #53656d;
    background: #fff;
    font:
      700 0.62rem/1 system-ui,
      sans-serif;
    cursor: help;
    vertical-align: 0.08rem;
  }
  .tip {
    position: absolute;
    z-index: 30;
    left: 50%;
    bottom: calc(100% + 0.5rem);
    width: min(15rem, 70vw);
    padding: 0.5rem 0.6rem;
    border: 1px solid #c9d2ce;
    border-radius: 0.3rem;
    background: #17211d;
    color: #fff;
    box-shadow: 0 0.35rem 1rem rgb(28 43 35 / 18%);
    font:
      400 0.72rem/1.35 system-ui,
      sans-serif;
    text-align: left;
    transform: translateX(-50%);
    opacity: 0;
    visibility: hidden;
    pointer-events: none;
  }
  .help:hover .tip,
  .help:focus .tip {
    opacity: 1;
    visibility: visible;
  }
  .help:focus-visible {
    outline: 2px solid var(--accent, #17583f);
    outline-offset: 2px;
  }
</style>
