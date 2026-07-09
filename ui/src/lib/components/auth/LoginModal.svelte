<script>
  import { auth } from '../../stores/authStore.svelte.ts'
  import Spinner from '../shared/Spinner.svelte'

  let username = $state('')
  let password = $state('')

  async function submit(e) {
    e?.preventDefault?.()
    if (auth.provider === 'clerk') {
      await auth.openClerkSignIn()
      return
    }
    if (!username.trim() || !password) return
    await auth.login(username.trim(), password)
  }
</script>

{#if auth.loginOpen}
  <div class="backdrop" role="presentation">
    <div class="modal" role="dialog" aria-modal="true" aria-labelledby="login-title">
      <h2 id="login-title" class="title">Sign in to VOLY</h2>

      {#if auth.provider === 'clerk'}
        <p class="hint">
          This server uses <strong>Clerk</strong>. Sign in with your organization account.
        </p>
        <div id="clerk-sign-in" class="clerk-host"></div>
        <div class="actions">
          <button type="button" class="btn primary" onclick={() => auth.openClerkSignIn()} disabled={auth.loading}>
            {#if auth.loading}<Spinner size={12} />{/if}
            Continue with Clerk
          </button>
        </div>
        {#if auth.error}
          <div class="error">{auth.error}</div>
        {/if}
      {:else}
        <p class="hint">
          JWT auth is enabled. Enter credentials from
          <code>auth.users</code> / <code>VOLY_AUTH_USERS</code>.
        </p>
        <form class="form" onsubmit={submit}>
          <label class="field">
            <span>Username</span>
            <input type="text" autocomplete="username" bind:value={username} disabled={auth.loading} required />
          </label>
          <label class="field">
            <span>Password</span>
            <input type="password" autocomplete="current-password" bind:value={password} disabled={auth.loading} required />
          </label>
          {#if auth.error}
            <div class="error">{auth.error}</div>
          {/if}
          <div class="actions">
            {#if !auth.enabled || auth.user}
              <button type="button" class="btn ghost" onclick={() => auth.closeLogin()}>Cancel</button>
            {/if}
            <button type="submit" class="btn primary" disabled={auth.loading || !username.trim() || !password}>
              {#if auth.loading}<Spinner size={12} />{/if}
              Sign in
            </button>
          </div>
        </form>
      {/if}
    </div>
  </div>
{/if}

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    z-index: 1000;
    display: flex;
    align-items: center;
    justify-content: center;
    background: color-mix(in srgb, #000 55%, transparent);
    backdrop-filter: blur(2px);
    padding: 16px;
  }

  .modal {
    width: min(420px, 100%);
    background: var(--bg-surface);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-md, 10px);
    padding: 20px;
    box-shadow: 0 16px 48px color-mix(in srgb, #000 35%, transparent);
  }

  .title {
    margin: 0 0 6px;
    font-size: 15px;
    font-weight: 600;
    color: var(--text-primary);
  }

  .hint {
    margin: 0 0 16px;
    font-size: 12px;
    color: var(--text-muted);
    line-height: 1.4;
  }

  .hint code {
    font-family: var(--font-mono);
    font-size: 11px;
  }

  .clerk-host {
    min-height: 40px;
    margin-bottom: 12px;
  }

  .form {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .field {
    display: flex;
    flex-direction: column;
    gap: 4px;
    font-size: 11px;
    color: var(--text-muted);
  }

  .field input {
    height: 32px;
    padding: 0 10px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-default);
    background: var(--bg-base, var(--bg-surface));
    color: var(--text-primary);
    font-size: 13px;
  }

  .field input:focus {
    outline: none;
    border-color: var(--accent-blue, #3b82f6);
  }

  .error {
    font-size: 12px;
    color: var(--accent-red, #ef4444);
    padding: 8px 10px;
    margin-top: 10px;
    border-radius: var(--radius-sm);
    background: color-mix(in srgb, var(--accent-red, #ef4444) 10%, transparent);
    border: 1px solid color-mix(in srgb, var(--accent-red, #ef4444) 25%, transparent);
  }

  .actions {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
    margin-top: 4px;
  }

  .btn {
    height: 30px;
    padding: 0 12px;
    border-radius: var(--radius-sm);
    font-size: 12px;
    font-weight: 600;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    border: 1px solid transparent;
    cursor: pointer;
  }

  .btn:disabled { opacity: 0.55; cursor: not-allowed; }

  .btn.primary {
    background: var(--accent-blue, #3b82f6);
    color: #fff;
  }

  .btn.ghost {
    background: transparent;
    color: var(--text-muted);
    border-color: var(--border-default);
  }

  .btn.ghost:hover {
    color: var(--text-primary);
    background: var(--bg-surface-hover);
  }
</style>
