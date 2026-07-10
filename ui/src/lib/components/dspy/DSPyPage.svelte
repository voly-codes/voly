<script>
  import { t } from '../../i18n/localeStore.svelte.ts'

  import { onMount } from 'svelte'
  import { AlertCircleIcon, ZapIcon, DatabaseIcon, LayersIcon } from '../../icons.js'
  import { fetchDSPyStatus } from '../../api/client.js'

  let data = $state(null)
  let loading = $state(true)
  let error = $state('')

  onMount(async () => {
    try {
      data = await fetchDSPyStatus()
    } catch (e) {
      error = e.message
    } finally {
      loading = false
    }
  })

  const modeLabel = (m) => t('dspy.mode.' + (m || 'off'))
  const modeDescOf = (m) => t('dspy.mode.' + (m || 'off') + '.desc')

  const lifecycleSteps = $derived([
    { label: t('dspy.action.dataset'), cmd: 'voly dspy dataset build', desc: t('dspy.action.dataset.desc') },
    { label: t('dspy.action.compile'), cmd: 'voly dspy compile --agent reviewer', desc: t('dspy.action.compile.desc') },
    { label: t('dspy.action.eval'), cmd: 'voly dspy eval --agent reviewer', desc: t('dspy.action.eval.desc') },
    { label: t('dspy.action.promote'), cmd: 'voly dspy promote reviewer.v1 --tag production', desc: t('dspy.action.promote.desc') },
  ])
</script>

<div class="dspy-page">
  <!-- Header -->
  <div class="page-header">
    <div class="header-left">
      <ZapIcon size="15" strokeWidth="2" />
      <span class="page-title">DSPy Optimizer</span>
      {#if data}
        <span class="mode-badge mode-{data.config.mode}">{modeLabel(data.config.mode)}</span>
      {/if}
    </div>
    <p class="header-desc">Слой оптимизации промптов. Компилирует агентские программы против датасетов телеметрии. Все вызовы идут через AIGateway — DLP, кэш и лимиты сохраняются.</p>
  </div>

  {#if loading}
    <div class="loading">Загрузка…</div>
  {:else if error}
    <div class="error-msg"><AlertCircleIcon size="13" strokeWidth="2" />{error}</div>
  {:else if data}
    <div class="content">

      <!-- Status strip -->
      <section class="section">
        <div class="section-title">Статус</div>
        <div class="status-strip">
          <div class="status-item">
            <span class="sl">Включён</span>
            {#if data.config.enabled}
              <span class="sv ok">да</span>
            {:else}
              <span class="sv muted">нет</span>
            {/if}
          </div>
          <div class="status-item">
            <span class="sl">Режим</span>
            <span class="sv mode-{data.config.mode}">{modeLabel(data.config.mode)}</span>
          </div>
          <div class="status-item">
            <span class="sl">Пакет dspy</span>
            {#if data.package.installed}
              <span class="sv ok">v{data.package.version}</span>
            {:else}
              <span class="sv warn">не установлен</span>
            {/if}
          </div>
          <div class="status-item">
            <span class="sl">Программы</span>
            <span class="sv">{data.programs.length}</span>
          </div>
          <div class="status-item">
            <span class="sl">Датасеты</span>
            <span class="sv">{data.datasets.length}</span>
          </div>
        </div>

        {#if !data.package.installed}
          <div class="install-hint">
            <AlertCircleIcon size="12" strokeWidth="2" />
            Установи пакет:
            <code>pip install -e ".[dspy]"</code>
            или
            <code>pip install "dspy&gt;=2.5.0"</code>
          </div>
        {/if}

        <p class="mode-desc">{modeDescOf(data.config.mode)}</p>
      </section>

      <!-- Config -->
      <section class="section">
        <div class="section-title">Конфигурация</div>
        <div class="config-grid">
          <div class="cfg-row"><span class="cfg-k">optimizer</span><code class="cfg-v">{data.config.optimizer}</code></div>
          <div class="cfg-row"><span class="cfg-k">compile_budget</span><code class="cfg-v">{data.config.compile_budget}</code></div>
          <div class="cfg-row"><span class="cfg-k">min_examples</span><code class="cfg-v">{data.config.min_examples}</code></div>
          <div class="cfg-row"><span class="cfg-k">active_tag</span><code class="cfg-v">{data.config.active_tag}</code></div>
          <div class="cfg-row"><span class="cfg-k">shadow_tag</span><code class="cfg-v">{data.config.shadow_tag}</code></div>
          <div class="cfg-row">
            <span class="cfg-k">agents</span>
            <span class="cfg-v">
              {#if data.config.agents.length}
                {#each data.config.agents as a}
                  <span class="agent-chip">{a}</span>
                {/each}
              {:else}
                <span class="muted-text">все агенты</span>
              {/if}
            </span>
          </div>
          <div class="cfg-row"><span class="cfg-k">programs_dir</span><code class="cfg-v">{data.config.programs_dir}</code></div>
          <div class="cfg-row"><span class="cfg-k">datasets_dir</span><code class="cfg-v">{data.config.datasets_dir}</code></div>
        </div>
      </section>

      <!-- Programs -->
      <section class="section">
        <div class="section-title">
          <LayersIcon size="12" strokeWidth="2" />
          Скомпилированные программы
        </div>
        {#if data.programs.length === 0}
          <div class="empty-hint">
            Нет скомпилированных программ. Сначала собери датасет, затем запусти
            <code>voly dspy compile --agent reviewer</code>
          </div>
        {:else}
          <div class="programs-table">
            <div class="table-head">
              <span>Program ID</span>
              <span>Агенты</span>
              <span>Версии</span>
              <span>Теги</span>
            </div>
            {#each data.programs as p}
              <div class="table-row">
                <span class="prog-id">{p.program_id}</span>
                <span class="prog-agents">
                  {#each p.agents as a}
                    <span class="agent-chip">{a}</span>
                  {/each}
                </span>
                <span class="prog-versions">
                  {#each p.versions as v}
                    <span class="ver-chip">v{v}{v === p.latest ? ' ★' : ''}</span>
                  {/each}
                </span>
                <span class="prog-tags">
                  {#each Object.entries(p.tags) as [tag, ver]}
                    <span class="tag-chip tag-{tag}">{tag}→v{ver}</span>
                  {:else}
                    <span class="muted-text">—</span>
                  {/each}
                </span>
              </div>
            {/each}
          </div>
        {/if}
      </section>

      <!-- Datasets -->
      <section class="section">
        <div class="section-title">
          <DatabaseIcon size="12" strokeWidth="2" />
          Датасеты
        </div>
        {#if data.datasets.length === 0}
          <div class="empty-hint">
            Нет датасетов. Запусти
            <code>voly dspy dataset build</code>
            чтобы собрать из событий телеметрии.
          </div>
        {:else}
          <div class="datasets-list">
            {#each data.datasets as ds}
              <div class="ds-row">
                <span class="ds-name">{ds.name}</span>
                <span class="ds-count">{ds.examples} примеров</span>
              </div>
            {/each}
          </div>
        {/if}
      </section>

      <!-- Lifecycle -->
      <section class="section">
        <div class="section-title">Жизненный цикл программы</div>
        <div class="lifecycle">
          {#each lifecycleSteps as step, i}
            <div class="lc-step">
              <div class="lc-num">{i + 1}</div>
              <div class="lc-body">
                <div class="lc-label">{step.label}</div>
                <code class="lc-cmd">{step.cmd}</code>
                <div class="lc-desc">{step.desc}</div>
              </div>
            </div>
            {#if i < lifecycleSteps.length - 1}
              <div class="lc-arrow">↓</div>
            {/if}
          {/each}
        </div>
      </section>

    </div>
  {/if}
</div>

<style>
  .dspy-page {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .page-header {
    padding: 12px 16px 10px;
    border-bottom: 1px solid var(--border-default);
    flex-shrink: 0;
  }

  .header-left {
    display: flex;
    align-items: center;
    gap: 8px;
    color: var(--text-muted);
    margin-bottom: 5px;
  }

  .page-title {
    font-size: 13px;
    font-weight: 600;
    color: var(--text-primary);
  }

  .header-desc {
    font-size: 11px;
    color: var(--text-muted);
    line-height: 1.5;
    margin: 0;
    max-width: 680px;
  }

  .mode-badge {
    font-size: 10px;
    font-weight: 600;
    padding: 1px 7px;
    border-radius: 10px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  .mode-shadow { background: color-mix(in srgb, var(--accent-amber) 15%, transparent); color: var(--accent-amber); }
  .mode-active { background: color-mix(in srgb, var(--accent-green) 15%, transparent); color: var(--accent-green); }
  .mode-off    { background: var(--bg-inset); color: var(--text-muted); }

  .loading, .error-msg {
    padding: 24px 16px;
    font-size: 12px;
    color: var(--text-muted);
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .error-msg { color: var(--accent-red); }

  .content {
    flex: 1;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 0;
  }

  .section {
    padding: 12px 16px;
    border-bottom: 1px solid var(--border-muted);
  }

  .section-title {
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--text-muted);
    margin-bottom: 10px;
    display: flex;
    align-items: center;
    gap: 5px;
  }

  /* Status strip */
  .status-strip {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-bottom: 8px;
  }

  .status-item {
    display: flex;
    align-items: center;
    gap: 5px;
    background: var(--bg-inset);
    border: 1px solid var(--border-muted);
    border-radius: var(--radius-sm);
    padding: 4px 8px;
  }

  .sl { font-size: 11px; color: var(--text-muted); }
  .sv { font-size: 11px; font-weight: 500; color: var(--text-secondary); }
  .sv.ok   { color: var(--accent-green); }
  .sv.warn { color: var(--accent-amber); }
  .sv.muted { color: var(--text-muted); }

  .install-hint {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
    font-size: 11px;
    color: var(--accent-amber);
    background: color-mix(in srgb, var(--accent-amber) 8%, transparent);
    border: 1px solid color-mix(in srgb, var(--accent-amber) 25%, transparent);
    border-radius: var(--radius-sm);
    padding: 6px 10px;
    margin-bottom: 8px;
  }

  .install-hint code {
    font-family: var(--font-mono);
    font-size: 10px;
    background: var(--bg-inset);
    border: 1px solid var(--border-muted);
    border-radius: 3px;
    padding: 1px 5px;
    color: var(--text-secondary);
  }

  .mode-desc {
    font-size: 11px;
    color: var(--text-muted);
    line-height: 1.5;
    margin: 0;
    font-style: italic;
  }

  /* Config */
  .config-grid {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .cfg-row {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    font-size: 11px;
  }

  .cfg-k {
    width: 120px;
    flex-shrink: 0;
    color: var(--text-muted);
    font-family: var(--font-mono);
  }

  .cfg-v {
    color: var(--text-secondary);
    font-family: var(--font-mono);
    display: flex;
    flex-wrap: wrap;
    gap: 3px;
  }

  .muted-text { color: var(--text-muted); font-style: italic; }

  /* Chips */
  .agent-chip {
    font-size: 10px;
    background: color-mix(in srgb, var(--accent-blue) 10%, transparent);
    border: 1px solid color-mix(in srgb, var(--accent-blue) 25%, transparent);
    color: var(--accent-blue);
    border-radius: var(--radius-sm);
    padding: 1px 5px;
    font-family: var(--font-mono);
  }

  .ver-chip {
    font-size: 10px;
    background: var(--bg-inset);
    border: 1px solid var(--border-muted);
    color: var(--text-muted);
    border-radius: var(--radius-sm);
    padding: 1px 5px;
    font-family: var(--font-mono);
  }

  .tag-chip {
    font-size: 10px;
    border-radius: var(--radius-sm);
    padding: 1px 5px;
    font-family: var(--font-mono);
    background: var(--bg-inset);
    border: 1px solid var(--border-muted);
    color: var(--text-muted);
  }
  .tag-chip.tag-production { background: color-mix(in srgb, var(--accent-green) 10%, transparent); border-color: color-mix(in srgb, var(--accent-green) 25%, transparent); color: var(--accent-green); }
  .tag-chip.tag-candidate  { background: color-mix(in srgb, var(--accent-amber) 10%, transparent); border-color: color-mix(in srgb, var(--accent-amber) 25%, transparent); color: var(--accent-amber); }

  /* Programs table */
  .programs-table {
    display: flex;
    flex-direction: column;
    gap: 2px;
    font-size: 11px;
  }

  .table-head {
    display: grid;
    grid-template-columns: 160px 1fr 1fr 1fr;
    gap: 8px;
    color: var(--text-muted);
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    padding: 0 6px 4px;
    border-bottom: 1px solid var(--border-muted);
  }

  .table-row {
    display: grid;
    grid-template-columns: 160px 1fr 1fr 1fr;
    gap: 8px;
    align-items: center;
    padding: 5px 6px;
    border-radius: var(--radius-sm);
    background: var(--bg-inset);
    border: 1px solid var(--border-muted);
  }

  .prog-id { font-family: var(--font-mono); font-size: 11px; color: var(--text-primary); }
  .prog-agents, .prog-versions, .prog-tags { display: flex; flex-wrap: wrap; gap: 3px; }

  /* Datasets */
  .datasets-list { display: flex; flex-direction: column; gap: 4px; }
  .ds-row {
    display: flex;
    align-items: center;
    gap: 10px;
    font-size: 11px;
    background: var(--bg-inset);
    border: 1px solid var(--border-muted);
    border-radius: var(--radius-sm);
    padding: 5px 10px;
  }
  .ds-name { font-family: var(--font-mono); color: var(--text-secondary); flex: 1; }
  .ds-count { color: var(--text-muted); }

  /* Empty hints */
  .empty-hint {
    font-size: 11px;
    color: var(--text-muted);
    line-height: 1.6;
  }
  .empty-hint code {
    font-family: var(--font-mono);
    font-size: 10px;
    background: var(--bg-inset);
    border: 1px solid var(--border-muted);
    border-radius: 3px;
    padding: 1px 5px;
    color: var(--text-secondary);
  }

  /* Lifecycle */
  .lifecycle {
    display: flex;
    flex-direction: column;
    gap: 0;
  }

  .lc-step {
    display: flex;
    gap: 12px;
    align-items: flex-start;
  }

  .lc-num {
    width: 22px;
    height: 22px;
    border-radius: 50%;
    background: color-mix(in srgb, var(--accent-blue) 12%, transparent);
    border: 1px solid color-mix(in srgb, var(--accent-blue) 30%, transparent);
    color: var(--accent-blue);
    font-size: 11px;
    font-weight: 600;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
  }

  .lc-body { padding-bottom: 6px; }
  .lc-label { font-size: 12px; font-weight: 500; color: var(--text-primary); margin-bottom: 3px; }
  .lc-cmd {
    display: block;
    font-family: var(--font-mono);
    font-size: 11px;
    background: var(--bg-inset);
    border: 1px solid var(--border-muted);
    border-radius: var(--radius-sm);
    padding: 3px 8px;
    color: var(--text-secondary);
    margin-bottom: 3px;
  }
  .lc-desc { font-size: 10px; color: var(--text-muted); }

  .lc-arrow {
    padding-left: 10px;
    font-size: 12px;
    color: var(--text-muted);
    line-height: 1;
    margin: 2px 0;
  }
</style>
