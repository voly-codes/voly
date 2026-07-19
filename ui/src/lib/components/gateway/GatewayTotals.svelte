<script>
  import { CoinsIcon, CpuIcon, ClockIcon, ZapIcon } from '../../icons.js'
  import { fmtTokens } from '../../utils/format.js'

  let { metrics } = $props()
</script>

<div class="totals-row">
  <div class="total-chip">
    <ZapIcon size="13" strokeWidth="2" />
    <span class="total-val">{metrics?.total_requests}</span>
    <span class="total-lbl">requests</span>
  </div>
  <div class="total-chip">
    <CpuIcon size="13" strokeWidth="2" />
    <span class="total-val">{fmtTokens(metrics?.total_tokens)}</span>
    <span class="total-lbl">tokens</span>
  </div>
  <div class="total-chip">
    <CoinsIcon size="13" strokeWidth="2" />
    <span class="total-val">${metrics?.total_cost_usd?.toFixed(4)}</span>
    <span class="total-lbl">total cost</span>
  </div>
  <div class="total-chip">
    <ClockIcon size="13" strokeWidth="2" />
    <span class="total-val">{metrics?.rpm}</span>
    <span class="total-lbl">current rpm</span>
  </div>
</div>

<style>
  .totals-row {
    display: flex;
    gap: 8px;
  }

  .total-chip {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
    padding: 10px 8px;
    background: var(--bg-surface);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-md);
    color: var(--text-muted);
  }

  .total-val {
    font-size: 14px;
    font-weight: 600;
    color: var(--text-primary);
    font-variant-numeric: tabular-nums;
  }

  .total-lbl {
    font-size: 9px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
</style>
