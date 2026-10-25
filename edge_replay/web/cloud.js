/* Private cloud snapshots. Only a publishable key and the current user's JWT leave this page. */
(() => {
  'use strict';
  class CloudClient {
    constructor(config, {fetch: request = globalThis.fetch.bind(globalThis), storage} = {}) {
      this.config = config; this.fetch = request;
      try { this.storage = storage || globalThis.sessionStorage; } catch (_) { this.storage = null; }
      this.storageKey = `cloud:${config.url}:${config.table}`; this.session = null; this.refreshing = null;
      try {
        const saved = JSON.parse(this.storage?.getItem(this.storageKey));
        if (saved?.access_token && saved?.refresh_token && saved?.user?.id) this.session = saved;
      } catch (_) { /* Storage unavailable or invalid: stay signed out. */ }
    }
    remember(value) {
      this.session = value?.access_token && value?.refresh_token && value?.user?.id ? {
        access_token: value.access_token, refresh_token: value.refresh_token,
        expires_at: value.expires_at || Math.floor(Date.now() / 1000) + value.expires_in,
        user: {id: value.user.id, email: value.user.email}
      } : null;
      try {
        if (this.session) this.storage?.setItem(this.storageKey, JSON.stringify(this.session));
        else this.storage?.removeItem(this.storageKey);
      } catch (_) { /* Memory-only session remains usable when storage is blocked. */ }
    }
    async request(path, {method = 'GET', body, token} = {}) {
      const headers = {apikey: this.config.publishableKey, 'Content-Type': 'application/json'};
      if (token) headers.Authorization = `Bearer ${token}`;
      const response = await this.fetch(this.config.url + path, {
        method, headers, ...(body === undefined ? {} : {body: JSON.stringify(body)}),
        credentials: 'omit', cache: 'no-store', redirect: 'error', signal: AbortSignal.timeout(20000)
      });
      const text = await response.text(); let result = null;
      try { result = text ? JSON.parse(text) : null; } catch (_) { /* Gateway may return plain text. */ }
      if (!response.ok) {
        const error = new Error(result?.msg || result?.message || result?.error_description || 'Cloud request failed. Try again shortly.');
        error.status = response.status; throw error;
      }
      return result;
    }
    async signIn(email, password) {
      const data = await this.request('/auth/v1/token?grant_type=password', {method: 'POST', body: {email, password}});
      this.remember(data); if (!this.session) throw new Error('Sign-in did not return a session.');
    }
    async signUp(email, password) {
      const data = await this.request('/auth/v1/signup', {method: 'POST', body: {email, password}});
      if (data?.access_token) this.remember(data);
      return Boolean(this.session);
    }
    async token() {
      if (!this.session) throw new Error('Sign in to access your cloud workspaces.');
      if (this.session.expires_at > Date.now() / 1000 + 60) return this.session.access_token;
      if (!this.refreshing) this.refreshing = (async () => {
        try {
          const data = await this.request('/auth/v1/token?grant_type=refresh_token', {
            method: 'POST', body: {refresh_token: this.session.refresh_token}});
          this.remember(data);
          if (!this.session) throw new Error('Your session ended. Sign in again.');
          return this.session.access_token;
        } catch (error) {
          if ([400, 401, 403].includes(error.status)) this.remember(null);
          throw error;
        } finally { this.refreshing = null; }
      })();
      return this.refreshing;
    }
    async signOut() {
      const token = this.session?.access_token;
      this.remember(null); // Always remove local credentials, including when the network is unavailable.
      if (token) await this.request('/auth/v1/logout?scope=local', {method: 'POST', token});
    }
    async rows(query = '', options = {}) {
      const token = await this.token();
      try { return await this.request(`/rest/v1/${this.config.table}${query}`, {...options, token}); }
      catch (error) { if (error.status === 401) this.remember(null); throw error; }
    }
    list() { return this.rows('?select=id,title,created_at&order=created_at.desc&limit=100'); }
    async save(title, payload) {
      title = title.trim();
      if (!title || title.length > 120) throw new Error('Use a workspace name between 1 and 120 characters.');
      if (!payload || Array.isArray(payload) || typeof payload !== 'object') throw new Error('No workspace is ready to save.');
      if (new TextEncoder().encode(JSON.stringify(payload)).length > this.config.maxPayloadBytes) throw new Error('This workspace exceeds the 8 MiB cloud limit. Export it locally instead.');
      await this.rows('', {method: 'POST', body: {title, payload, owner_id: this.session?.user.id}});
    }
    async load(id) {
      if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id)) throw new Error('Invalid workspace identifier.');
      const rows = await this.rows(`?id=eq.${encodeURIComponent(id)}&select=payload&limit=1`);
      if (!rows?.length) throw new Error('Workspace no longer exists or is unavailable.');
      return rows[0].payload;
    }
    async remove(id) {
      if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id)) throw new Error('Invalid workspace identifier.');
      await this.rows(`?id=eq.${encodeURIComponent(id)}`, {method: 'DELETE'});
    }
  }
  function init({getSnapshot, onLoad, kind = 'workspace', title = 'Cloud workspaces'} = {}) {
    const dialog = document.createElement('dialog'); dialog.className = 'cloud-dialog';
    dialog.setAttribute('aria-label', title);
    // Fixed markup only. Remote values are always inserted through textContent.
    dialog.innerHTML = `<header class="cloud-header"><div><small>PRIVATE CLOUD STORAGE</small><h2></h2></div><button type="button" class="cloud-close" aria-label="Close cloud workspaces">×</button></header>
      <p class="cloud-description">Save a copy to your account and open it on another device. A cloud copy is created only when you choose Save. It is separate from your working session.</p>
      <p class="cloud-status" role="status" aria-live="polite"></p>
      <form class="cloud-auth"><label>Email<input name="email" type="email" autocomplete="username" required maxlength="254"></label><label>Password<input name="password" type="password" autocomplete="current-password" required minlength="6"></label><div class="cloud-actions"><button type="submit">Sign in</button><button type="button" class="cloud-signup">Create account</button></div><p>Creating an account may send a confirmation email. Confirm it, then return here to sign in. Sessions are kept for this browser tab.</p></form>
      <section class="cloud-account" hidden><div class="cloud-account-line"><span class="cloud-email"></span><button type="button" class="cloud-signout">Sign out</button></div><form class="cloud-save"><label>Workspace name<input name="title" maxlength="120" required></label><button type="submit">Save a new copy</button></form><div class="cloud-list-heading"><h3>Saved workspaces</h3><button type="button" class="cloud-refresh">Refresh</button></div><ul class="cloud-list"></ul></section>`;
    document.body.append(dialog);
    const $ = selector => dialog.querySelector(selector);
    $('h2').textContent = title;
    $('.cloud-save input').value = `${kind} · ${new Date().toLocaleDateString()}`;
    $('.cloud-save').hidden = typeof getSnapshot !== 'function';
    let client, opening, busy = false;
    const status = (message, error = false) => { $('.cloud-status').textContent = message; $('.cloud-status').classList.toggle('cloud-error', error); };
    const render = () => {
      const signedIn = Boolean(client?.session);
      $('.cloud-auth').hidden = signedIn; $('.cloud-account').hidden = !signedIn;
      $('.cloud-email').textContent = client?.session?.user.email || 'Signed in';
    };
    const action = async operation => {
      if (busy) return;
      busy = true; dialog.setAttribute('aria-busy', 'true');
      const controls = [...dialog.querySelectorAll('button,input')].filter(node => !node.classList.contains('cloud-close'));
      controls.forEach(node => { node.disabled = true; });
      try { await operation(); } catch (error) { status(error.message || 'Unable to connect. Check your connection and try again.', true); }
      finally { busy = false; dialog.removeAttribute('aria-busy'); controls.forEach(node => { node.disabled = false; }); render(); }
    };
    const list = async () => {
      const rows = await client.list(); const container = $('.cloud-list'); container.replaceChildren();
      if (!rows.length) { const item = document.createElement('li'); item.textContent = 'No saved workspaces yet.'; container.append(item); }
      for (const row of rows) {
        const item = document.createElement('li'), text = document.createElement('div'), label = document.createElement('strong'), date = document.createElement('small');
        label.textContent = row.title; date.textContent = new Date(row.created_at).toLocaleString(); text.append(label, date); item.append(text);
        if (typeof onLoad === 'function') {
          const load = document.createElement('button'); load.type = 'button'; load.textContent = 'Open';
          load.onclick = () => action(async () => {
            if (!globalThis.confirm('Open this saved copy? It will replace the current workspace view.')) return;
            await onLoad(await client.load(row.id)); dialog.close();
          }); item.append(load);
        }
        const remove = document.createElement('button'); remove.type = 'button'; remove.textContent = 'Delete'; remove.className = 'cloud-delete';
        remove.onclick = () => action(async () => {
          if (!globalThis.confirm('Permanently delete this cloud copy?')) return;
          await client.remove(row.id); await list(); status('Cloud copy deleted.');
        }); item.append(remove); container.append(item);
      }
    };
    dialog.addEventListener('close', () => { $('.cloud-auth [name=password]').value = ''; });
    $('.cloud-close').onclick = () => dialog.close();
    $('.cloud-auth').onsubmit = event => { event.preventDefault(); action(async () => {
      await client.signIn($('.cloud-auth [name=email]').value.trim(), $('.cloud-auth [name=password]').value);
      $('.cloud-auth [name=password]').value = ''; render(); await list(); status('Signed in. Your saved workspaces are private to your account.');
    }); };
    $('.cloud-signup').onclick = () => {
      if (!$('.cloud-auth').reportValidity()) return;
      action(async () => {
        const signedIn = await client.signUp($('.cloud-auth [name=email]').value.trim(), $('.cloud-auth [name=password]').value);
        $('.cloud-auth [name=password]').value = ''; render();
        if (signedIn) await list();
        status(signedIn ? 'Account ready.' : 'Check your email for a confirmation link, then return here to sign in.');
      });
    };
    $('.cloud-signout').onclick = () => action(async () => { try { await client.signOut(); } finally { $('.cloud-list').replaceChildren(); status('Signed out on this device.'); } });
    $('.cloud-refresh').onclick = () => action(async () => { await list(); status('Workspaces refreshed.'); });
    $('.cloud-save').onsubmit = event => { event.preventDefault(); action(async () => {
      await client.save($('.cloud-save [name=title]').value, await getSnapshot()); await list(); status('Private cloud copy saved.');
    }); };
    return {open: async () => {
      if (!dialog.open) dialog.showModal();
      if (opening || busy) return;
      opening = true;
      await action(async () => {
        if (!client) {
          status('Connecting to cloud storage…'); $('.cloud-auth').hidden = true;
          const response = await fetch('/api/cloud/config', {cache: 'no-store'});
          if (!response.ok) throw new Error('Cloud configuration is unavailable.');
          const config = await response.json();
          if (!config.configured) { status(config.message || 'Cloud is not configured.'); return; }
          client = new CloudClient(config);
        }
        render();
        if (client.session) { await list(); status('Your private saved workspaces.'); }
        else status('Sign in to save and open private cloud copies.');
      });
      if (!client) { $('.cloud-auth').hidden = true; $('.cloud-account').hidden = true; }
      opening = false;
    }, close: () => dialog.close()};
  }
  globalThis.CloudWorkspace = {init, Client: CloudClient};
})();
