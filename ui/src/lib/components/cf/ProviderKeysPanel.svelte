<script>
  import { t } from '../../i18n/localeStore.svelte.ts'

  import { onMount } from 'svelte'
  import { CheckIcon, AlertCircleIcon } from '../../icons.js'
  import { createProviderKey, deleteProviderKey, fetchProviderKeys } from '../../api/client.js'

  const PROVIDERS = ['anthropic', 'openai', 'google-ai-studio', 'deepseek']

  let data = $state(null)
  let loading = $state(true)
  let error = $state('')
  let provider = $state('anthropic')
  let keyValue = $state('')
  let saving = $state(false)
  let notice = $state('')

  onMount(load)

  async function load() {
    loading = true
    error = ''
    try { data = await fetchProviderKeys() }
    catch (e) { error = e.message }
    finally { loading = false }
  }

  async function save() {
    if (!keyValue.trim() || saving) return
    saving = true
    error = ''
    notice = ''
    try {
      const res = await createProviderKey(provider, keyValue.trim())
      notice = res.name
      keyValue = ''
      await load()
    } catch (e) { error = e.message }
    finally { saving = false }
  }

  async function remove(p, alias) {
    error = ''
    try {
      await deleteProviderKey(p, alias)
      await load()
    } catch (e) { error = e.message }
  }
</script>

<section class="cf-section">
  <div class="section-header">
    <span class="section-title">{t('cf.byok')}</span>
    {#if data}
      <span class="byok-state" class:on={data.byok_enabled}>
        {data.byok_enabled ? t('cf.byokOn') : t('cf.byokOff')}
      </span>
    {/if}
  </div>
  <p class="section-desc">{t('cf.byokDesc')}</p>

  {#if loading}
    <div class="loading-text">{t('cf.loading')}</div>
  {:else if data && !data.configured}
    <div class="not-configured-msg">
      <AlertCircleIcon size="14" strokeWidth="2" />
      <div>
        <div>{data.hint ?? t('cf.byokNotConfigured')}</div>
        <code class="env-hint">CLOUDFLARE_ACCOUNT_ID / CLOUDFLARE_API_TOKEN</code>
      </div>
    </div>
  {:else}
    <form class="byok-form" onsubmit={e => { e.preventDefault(); save() }}>
      <select bind:value={provider} class="byok-select">
        {#each PROVIDERS as p}
          <option value={p}>{p}</option>
        {/each}
      </select>
      <input
        type="password"
        class="byok-input"
        placeholder={t('cf.byokKeyPlaceholder')}
        bind:value={keyValue}
        autocomplete="off"
      />
      <button class="byok-save" type="submit" disabled={saving || !keyValue.trim()}>
        {t('cf.byokAdd')}
      </button>
    </form>

    {#if notice}
      <div class="byok-notice">
        <CheckIcon size="12" strokeWidth="2.5" style="color: var(--accent-green)" />
        {notice}
      </div>
    {/if}
    {#if error}
      <div class="spend-error">
        <AlertCircleIcon size="13" strokeWidth="2" />
        {error}
      </div>
    {/if}

    <div class="byok-list">
      <div class="byok-list-title">{t('cf.byokStored')}</div>
      {#if data?.error}
        <div class="spend-error">{data.error}</div>
      {:else if !data?.keys?.length}
        <div class="loading-text">{t('cf.byokNone')}</div>
      {:else}
        {#each data.keys as k}
          <div class="byok-row">
            <span class="byok-provider">{k.provider}</span>
            <code class="byok-name">{k.name}</code>
            <button class="byok-del" onclick={() => remove(k.provider, k.alias)}>
              {t('cf.byokDelete')}
            </button>
          </div>
        {/each}
      {/if}
    </div>
  {/if}
</section>

<style>
  /* Section chrome mirrors CFPage.svelte (scoped there, so duplicated here). */
  .cf-section {
    padding: 14px 16px;
    border-bottom: 1px solid var(--border-default);
  }
  .section-header {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 12px;
  }
  .section-title {
    font-size: 12px;
    font-weight: 600;
    color: var(--text-primary);
    display: flex;
    align-items: center;
    gap: 5px;
    flex: 1;
  }
  .section-desc {
    font-size: 11px;
    color: var(--text-muted);
    line-height: 1.5;
    margin: 0 0 10px;
  }
  .loading-text { font-size: 12px; color: var(--text-muted); padding: 4px 0; }
  .not-configured-msg {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    color: var(--accent-amber);
    font-size: 12px;
  }
  .env-hint { display: block; font-size: 10px; color: var(--text-muted); margin-top: 4px; }
  .spend-error {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    color: var(--accent-red);
  }

  .byok-state {
    font-size: 11px;
    color: var(--text-muted);
  }
  .byok-state.on {
    color: var(--accent-green);
  }
  .byok-form {
    display: flex;
    gap: 8px;
    margin: 8px 0;
  }
  .byok-select,
  .byok-input {
    background: var(--bg-inset);
    border: 1px solid var(--border-muted);
    border-radius: var(--radius-sm);
    color: var(--text-primary);
    font-size: 12px;
    padding: 6px 8px;
  }
  .byok-input {
    flex: 1;
    min-width: 0;
  }
  .byok-save {
    background: var(--accent-blue);
    border: none;
    border-radius: var(--radius-sm);
    color: var(--accent-blue-foreground);
    cursor: pointer;
    font-size: 12px;
    padding: 6px 12px;
  }
  .byok-save:disabled {
    opacity: 0.5;
    cursor: default;
  }
  .byok-notice {
    align-items: center;
    display: flex;
    font-size: 11px;
    gap: 6px;
    color: var(--text-secondary);
    margin-bottom: 6px;
  }
  .byok-list-title {
    color: var(--text-muted);
    font-size: 11px;
    margin: 8px 0 4px;
    text-transform: uppercase;
  }
  .byok-row {
    align-items: center;
    display: flex;
    gap: 10px;
    padding: 4px 0;
  }
  .byok-provider {
    font-size: 12px;
    font-weight: 600;
    min-width: 120px;
    color: var(--text-primary);
  }
  .byok-name {
    color: var(--text-muted);
    flex: 1;
    font-family: var(--font-mono);
    font-size: 11px;
  }
  .byok-del {
    background: none;
    border: 1px solid var(--border-muted);
    border-radius: var(--radius-sm);
    color: var(--text-secondary);
    cursor: pointer;
    font-size: 11px;
    padding: 2px 8px;
  }
  .byok-del:hover {
    color: var(--accent-red);
  }
</style>
