/* Global Caché iTach – visual IR code editor panel for Home Assistant.
 * Plain web component, no build step. Talks to the backend over websocket.
 */
const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const errMsg = (e) => (e && (e.message || e.error?.message)) || String(e);
const byName = (a, b) => a[1].name.localeCompare(b[1].name, undefined, { numeric: true });

const FORMAT_LABEL = {
  sendir: "Global Caché sendir",
  raw: "Global Caché (no header)",
  compressed: "Global Caché (compressed)",
  pronto: "Pronto hex",
};

const STYLE = `
:host { display:block; height:100%; background:var(--primary-background-color); color:var(--primary-text-color);
  font-family:var(--paper-font-body1_-_font-family, Roboto, system-ui, sans-serif); --r:12px; }
* { box-sizing:border-box; }
[hidden] { display:none !important; }
.toolbar { display:flex; align-items:center; gap:8px; height:var(--header-height,56px); padding:0 12px;
  background:var(--app-header-background-color, var(--primary-color)); color:var(--app-header-text-color, #fff);
  border-bottom:1px solid var(--app-header-border-bottom, transparent); }
.toolbar .title { font-size:20px; font-weight:400; margin-left:4px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.spacer { flex:1; }
.toolbar select, .toolbar .tbtn { background:rgba(255,255,255,.15); color:inherit; border:0; border-radius:8px; padding:7px 10px; font:inherit; font-size:14px; cursor:pointer; }
.toolbar select option { color:#000; }
.toolbar .tbtn:hover { background:rgba(255,255,255,.25); }
.content { display:grid; grid-template-columns:280px 1fr; gap:16px; padding:16px; max-width:1300px; margin:0 auto; }
:host([narrow]) .content { grid-template-columns:1fr; padding:12px; }
.card { background:var(--card-background-color, #fff); border-radius:var(--ha-card-border-radius, var(--r));
  box-shadow:var(--ha-card-box-shadow, 0 1px 3px rgba(0,0,0,.12)); border:1px solid var(--ha-card-border-color, var(--divider-color, #e0e0e0)); }
.devices { padding:8px; align-self:start; }
.devices h2, .cmds h2 { font-size:14px; text-transform:uppercase; letter-spacing:.06em; color:var(--secondary-text-color); margin:8px 8px 10px; font-weight:500; }
.dev { display:flex; flex-direction:column; align-items:flex-start; width:100%; padding:10px 12px; margin:2px 0; border:0; border-radius:10px;
  background:transparent; color:inherit; font:inherit; text-align:left; cursor:pointer; }
.dev:hover { background:var(--secondary-background-color, rgba(0,0,0,.05)); }
.dev.sel { background:rgba(var(--rgb-primary-color, 3,169,244), .14); color:var(--primary-color); }
.dev .n { font-weight:500; font-size:15px; }
.dev .s { font-size:12px; color:var(--secondary-text-color); margin-top:2px; }
.add { width:100%; margin-top:6px; padding:10px; border:1.5px dashed var(--divider-color, #ccc); border-radius:10px; background:transparent;
  color:var(--primary-color); font:inherit; font-weight:500; cursor:pointer; }
.add:hover { border-color:var(--primary-color); }
.cmds { padding:16px; min-height:240px; }
.dhead { display:flex; align-items:center; gap:10px; flex-wrap:wrap; margin-bottom:14px; }
.dhead .dn { font-size:22px; font-weight:400; }
.chip { font-size:12px; padding:3px 9px; border-radius:99px; background:var(--secondary-background-color, #eee); color:var(--secondary-text-color); }
.grid { display:grid; grid-template-columns:repeat(auto-fill, minmax(170px, 1fr)); gap:10px; }
.cmd { border:1px solid var(--divider-color, #e0e0e0); border-radius:var(--r); padding:12px; display:flex; flex-direction:column; gap:8px; }
.cmd .n { font-weight:500; word-break:break-word; }
.cmd .m { font-size:12px; color:var(--secondary-text-color); }
.cmd .row { display:flex; gap:6px; margin-top:auto; }
.btn { border:0; border-radius:8px; padding:8px 14px; font:inherit; font-size:14px; font-weight:500; cursor:pointer;
  background:var(--secondary-background-color, #eee); color:var(--primary-text-color); display:inline-flex; align-items:center; gap:6px; justify-content:center; }
.btn:hover { filter:brightness(.95); }
.btn:disabled { opacity:.5; cursor:default; }
.btn.primary { background:var(--primary-color); color:var(--text-primary-color, #fff); }
.btn.danger { background:transparent; color:var(--error-color, #db4437); }
.btn.ghost { background:transparent; color:var(--primary-color); }
.btn.grow { flex:1; }
.tile { border:1.5px dashed var(--divider-color, #ccc); border-radius:var(--r); padding:12px; min-height:96px; background:transparent;
  color:var(--primary-color); font:inherit; font-weight:500; cursor:pointer; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:4px; }
.tile:hover { border-color:var(--primary-color); }
.tile .big { font-size:22px; }
.empty { text-align:center; padding:48px 16px; color:var(--secondary-text-color); }
.empty .big { font-size:44px; margin-bottom:8px; }
.empty p { max-width:420px; margin:8px auto; line-height:1.5; }
/* modal */
.scrim { position:fixed; inset:0; background:rgba(0,0,0,.45); display:flex; align-items:center; justify-content:center; padding:16px; z-index:10; }
.modal { width:min(640px, 100%); max-height:calc(100vh - 32px); overflow:auto; padding:20px; }
.modal h3 { margin:0 0 16px; font-size:20px; font-weight:400; }
label.f { display:block; margin-bottom:14px; font-size:13px; color:var(--secondary-text-color); }
label.f > input, label.f > select, label.f > textarea { display:block; width:100%; margin-top:5px; padding:10px 12px; font:inherit; font-size:15px;
  color:var(--primary-text-color); background:var(--input-fill-color, var(--secondary-background-color, #f5f5f5));
  border:1px solid var(--divider-color, #ccc); border-radius:8px; outline:none; }
label.f > input:focus, label.f > select:focus, label.f > textarea:focus { border-color:var(--primary-color); }
textarea { font-family:ui-monospace, SFMono-Regular, Menlo, Consolas, monospace !important; font-size:13px !important; min-height:120px; resize:vertical; word-break:break-all; }
.two { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
.info { display:flex; align-items:center; gap:8px; flex-wrap:wrap; font-size:13px; margin:-6px 0 10px; min-height:24px; }
.badge { padding:3px 9px; border-radius:99px; font-size:12px; font-weight:500; }
.badge.ok { background:rgba(67,160,71,.15); color:var(--success-color, #43a047); }
.badge.bad { background:rgba(219,68,55,.13); color:var(--error-color, #db4437); }
.info .m { color:var(--secondary-text-color); }
.wave { width:100%; height:64px; display:flex; align-items:center; justify-content:center; overflow:hidden; border-radius:8px; background:var(--secondary-background-color, #f3f3f3); margin-bottom:14px; }
.wave .sig { stroke:var(--primary-color); fill:none; stroke-width:1.5; vector-effect:non-scaling-stroke; }
.wave .rep { fill:rgba(var(--rgb-primary-color, 3,169,244), .12); }
.wave svg { width:100%; height:100%; display:block; }
.wave .wempty { color:var(--secondary-text-color); font-size:12px; }
.learn { display:flex; align-items:center; gap:12px; padding:12px; border-radius:10px; background:rgba(var(--rgb-primary-color, 3,169,244), .1); margin-bottom:14px; font-size:14px; }
.pulse { width:14px; height:14px; border-radius:50%; background:var(--primary-color); animation:p 1s infinite; flex:none; }
@keyframes p { 0%{transform:scale(.7);opacity:1} 100%{transform:scale(1.6);opacity:0} }
.actions { display:flex; gap:8px; flex-wrap:wrap; align-items:center; margin-top:6px; }
.hint { font-size:12px; color:var(--secondary-text-color); margin:-8px 0 14px; line-height:1.45; }
.chk { display:flex; gap:8px; align-items:center; font-size:14px; margin-bottom:14px; }
.toast { position:fixed; left:50%; bottom:24px; transform:translateX(-50%); background:#323232; color:#fff; padding:12px 18px; border-radius:10px;
  font-size:14px; z-index:20; max-width:min(560px, calc(100% - 32px)); white-space:pre-line; box-shadow:0 4px 14px rgba(0,0,0,.3); }
.toast.err { background:var(--error-color, #c62828); }
`;

class ItachGcPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._entries = [];
    this._entryId = null;
    this._devices = {};
    this._selDev = null;
    this._loading = true;
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    const mb = this.shadowRoot.querySelector("ha-menu-button");
    if (mb) mb.hass = hass;
    if (first) this._init();
  }
  get hass() { return this._hass; }
  set narrow(v) {
    this._narrow = v;
    this.toggleAttribute("narrow", !!v);
    const mb = this.shadowRoot.querySelector("ha-menu-button");
    if (mb) mb.narrow = v;
  }
  set panel(v) { this._panel = v; }
  set route(v) { this._route = v; }

  ws(type, data = {}) {
    return this._hass.callWS({ type: `itach_gc/${type}`, ...data });
  }

  get _entry() { return this._entries.find((e) => e.entry_id === this._entryId); }
  get _connectors() { return this._entry?.connectors?.length ? this._entry.connectors : ["1:1"]; }

  async _init() {
    this.shadowRoot.innerHTML = `<style>${STYLE}</style>
      <div class="toolbar"></div><div class="content-wrap"></div>
      <div id="modal"></div><div id="toast"></div>`;
    this.shadowRoot.addEventListener("click", (ev) => this._onClick(ev));
    this.shadowRoot.addEventListener("change", (ev) => {
      if (ev.target.id === "entry") { this._entryId = ev.target.value; this._selDev = null; this._load(); }
    });
    window.addEventListener("keydown", (ev) => { if (ev.key === "Escape" && this._modalOpen) this._closeModal(); });
    this._renderToolbar();
    this._render();
    try {
      this._entries = await this.ws("entries");
      const firstLoaded = this._entries.find((e) => e.loaded) || this._entries[0];
      this._entryId = firstLoaded?.entry_id ?? null;
      await this._load();
    } catch (e) {
      this._loading = false;
      this._render();
      this._toast(errMsg(e), true);
    }
  }

  async _load() {
    this._loading = true;
    this._renderToolbar();
    this._render();
    try {
      if (this._entryId && this._entry?.loaded) {
        this._devices = (await this.ws("codes", { entry_id: this._entryId })).devices;
      } else this._devices = {};
      if (!this._devices[this._selDev]) this._selDev = Object.entries(this._devices).sort(byName)[0]?.[0] ?? null;
    } catch (e) {
      this._devices = {};
      this._toast(errMsg(e), true);
    }
    this._loading = false;
    this._render();
  }

  async _reload() {
    this._devices = (await this.ws("codes", { entry_id: this._entryId })).devices;
    if (!this._devices[this._selDev]) this._selDev = Object.entries(this._devices).sort(byName)[0]?.[0] ?? null;
    this._render();
  }

  // ---------- rendering ----------
  _renderToolbar() {
    const tb = this.shadowRoot.querySelector(".toolbar");
    const entrySel = this._entries.length > 1
      ? `<select id="entry" aria-label="iTach">${this._entries.map((e) =>
          `<option value="${esc(e.entry_id)}" ${e.entry_id === this._entryId ? "selected" : ""}>${esc(e.title)}${e.loaded ? "" : " (offline)"}</option>`).join("")}</select>`
      : "";
    const canIO = this._entry?.loaded;
    tb.innerHTML = `<ha-menu-button></ha-menu-button>
      <div class="title">iTach IR codes</div><div class="spacer"></div>${entrySel}
      ${canIO ? `<button class="tbtn" data-a="import" title="Import codes">⬆ Import</button>
      <button class="tbtn" data-a="export" title="Export codes">⬇ Export</button>` : ""}`;
    const mb = tb.querySelector("ha-menu-button");
    mb.hass = this._hass;
    mb.narrow = this._narrow;
  }

  _render() {
    const wrap = this.shadowRoot.querySelector(".content-wrap");
    if (!wrap) return;
    if (this._loading) { wrap.innerHTML = `<div class="empty"><div class="big">⏳</div>Loading…</div>`; return; }
    if (!this._entries.length) {
      wrap.innerHTML = `<div class="empty"><div class="big">📡</div><h2>No iTach added yet</h2>
        <p>Go to <b>Settings → Devices &amp; services → Add integration</b> and search for <b>Global Caché iTach IR</b>.</p></div>`;
      return;
    }
    if (!this._entry?.loaded) {
      wrap.innerHTML = `<div class="empty"><div class="big">🔌</div><h2>This iTach is offline</h2>
        <p>Home Assistant can't reach <b>${esc(this._entry?.host)}</b> right now. Check it's powered on and on the network – it'll retry by itself.</p></div>`;
      return;
    }
    const devs = Object.entries(this._devices).sort(byName);
    const devList = devs.map(([id, d]) => {
      const n = Object.keys(d.commands).length;
      return `<button class="dev ${id === this._selDev ? "sel" : ""}" data-a="sel" data-dev="${esc(id)}">
        <span class="n">${esc(d.name)}</span><span class="s">Port ${esc(d.connector)} · ${n} code${n === 1 ? "" : "s"}</span></button>`;
    }).join("");

    wrap.innerHTML = `<div class="content">
      <div class="card devices"><h2>Devices</h2>${devList || ""}
        <button class="add" data-a="add-dev">+ Add device</button></div>
      <div class="card cmds">${this._renderCommands()}</div></div>`;
  }

  _renderCommands() {
    const dev = this._devices[this._selDev];
    if (!dev) {
      return `<div class="empty"><div class="big">📺</div><h2>Add your first device</h2>
        <p>A device is the thing you're controlling – like “Living room TV” or “Soundbar”. Then you add its IR codes.</p>
        <button class="btn primary" data-a="add-dev">+ Add device</button></div>`;
    }
    const cmds = Object.entries(dev.commands).sort(byName);
    const cards = cmds.map(([id, c]) => `<div class="cmd">
        <div class="n">${esc(c.name)}</div>
        <div class="m">${c.repeat ? `repeat ×${esc(c.repeat)}` : "&nbsp;"}</div>
        <div class="row">
          <button class="btn primary grow" data-a="send" data-cmd="${esc(id)}" title="Send now">▶ Send</button>
          <button class="btn" data-a="edit-cmd" data-cmd="${esc(id)}" title="Edit" aria-label="Edit ${esc(c.name)}">✎</button>
        </div></div>`).join("");
    return `<div class="dhead"><span class="dn">${esc(dev.name)}</span><span class="chip">IR port ${esc(dev.connector)}</span>
        <span class="spacer"></span><button class="btn ghost" data-a="edit-dev">⚙ Device settings</button></div>
      <div class="grid">${cards}
        <button class="tile" data-a="add-cmd"><span class="big">＋</span>Add code</button>
        <button class="tile" data-a="add-cmd" data-learn="1"><span class="big">📡</span>Learn from remote</button>
      </div>`;
  }

  // ---------- events ----------
  async _onClick(ev) {
    const el = ev.target.closest("[data-a]");
    if (!el) {
      if (ev.target.classList?.contains("scrim")) this._closeModal();
      return;
    }
    const a = el.dataset.a;
    try {
      switch (a) {
        case "sel": this._selDev = el.dataset.dev; this._render(); break;
        case "add-dev": this._deviceDialog(null); break;
        case "edit-dev": this._deviceDialog(this._selDev); break;
        case "add-cmd": this._codeDialog(null, !!el.dataset.learn); break;
        case "edit-cmd": this._codeDialog(el.dataset.cmd); break;
        case "send": await this._sendStored(el, el.dataset.cmd); break;
        case "export": await this._export(); break;
        case "import": this._importDialog(); break;
        case "close": this._closeModal(); break;
      }
    } catch (e) {
      this._toast(errMsg(e), true);
    }
  }

  async _sendStored(btn, cmdId) {
    const dev = this._devices[this._selDev];
    const c = dev.commands[cmdId];
    btn.disabled = true;
    try {
      await this.ws("send", { entry_id: this._entryId, code: c.code, connector: dev.connector, repeat: c.repeat ?? null });
      this._toast(`Sent “${c.name}” ✨`);
    } finally { btn.disabled = false; }
  }

  // ---------- modal helpers ----------
  _openModal(html) {
    const m = this.shadowRoot.getElementById("modal");
    m.innerHTML = `<div class="scrim"><div class="card modal" role="dialog" aria-modal="true">${html}</div></div>`;
    this._modalOpen = true;
    const first = m.querySelector("input, textarea, select");
    if (first) setTimeout(() => first.focus(), 30);
    return m.querySelector(".modal");
  }
  _closeModal() {
    this._modalOpen = false;
    this._learnAbort = true;
    this.shadowRoot.getElementById("modal").innerHTML = "";
  }

  _toast(msg, isErr = false) {
    const t = this.shadowRoot.getElementById("toast");
    t.innerHTML = `<div class="toast ${isErr ? "err" : ""}" role="status">${esc(msg)}</div>`;
    clearTimeout(this._toastT);
    this._toastT = setTimeout(() => (t.innerHTML = ""), isErr ? 6000 : 2600);
  }

  // ---------- device dialog ----------
  _deviceDialog(devId) {
    const dev = devId ? this._devices[devId] : null;
    const opts = this._connectors.map((c) =>
      `<option value="${esc(c)}" ${(dev?.connector ?? this._connectors[0]) === c ? "selected" : ""}>Port ${esc(c)}</option>`).join("");
    const m = this._openModal(`<h3>${dev ? "Device settings" : "New device"}</h3>
      <label class="f">Name<input id="dname" maxlength="64" placeholder="e.g. Living room TV" value="${esc(dev?.name ?? "")}"></label>
      <label class="f">IR output (which emitter / blaster it's on)<select id="dconn">${opts}</select></label>
      <div class="actions">
        ${dev ? `<button class="btn danger" id="ddel">🗑 Delete device</button>` : ""}
        <span class="spacer"></span>
        <button class="btn" data-a="close">Cancel</button>
        <button class="btn primary" id="dsave">Save</button></div>`);
    const save = async () => {
      const btn = m.querySelector("#dsave");
      btn.disabled = true;
      try {
        const res = await this.ws("device/save", {
          entry_id: this._entryId, device_id: devId, name: m.querySelector("#dname").value, connector: m.querySelector("#dconn").value,
        });
        this._selDev = res.device_id;
        this._closeModal();
        await this._reload();
        this._toast(dev ? "Device saved 💾" : "Device added 🎉");
      } catch (e) { this._toast(errMsg(e), true); btn.disabled = false; }
    };
    m.querySelector("#dsave").onclick = save;
    m.querySelector("#dname").onkeydown = (e) => { if (e.key === "Enter") save(); };
    const del = m.querySelector("#ddel");
    if (del) del.onclick = async () => {
      const n = Object.keys(dev.commands).length;
      if (!confirm(`Delete “${dev.name}”${n ? ` and its ${n} code${n === 1 ? "" : "s"}` : ""}? This also removes its button entities.`)) return;
      try {
        await this.ws("device/delete", { entry_id: this._entryId, device_id: devId });
        this._closeModal();
        this._selDev = null;
        await this._reload();
        this._toast("Device deleted");
      } catch (e) { this._toast(errMsg(e), true); }
    };
  }

  // ---------- code dialog ----------
  _codeDialog(cmdId, autoLearn = false) {
    const dev = this._devices[this._selDev];
    const c = cmdId ? dev.commands[cmdId] : null;
    const m = this._openModal(`<h3>${c ? "Edit code" : "New code"} <span class="chip">${esc(dev.name)}</span></h3>
      <label class="f">Button name<input id="cname" maxlength="64" placeholder="e.g. Power, Volume up, HDMI 1" value="${esc(c?.name ?? "")}"></label>
      <div id="learnbox"></div>
      <label class="f">IR code<textarea id="ccode" spellcheck="false" placeholder="sendir,1:1,1,38000,1,1,342,171,21,21,21,64,…   or   0000 006D 0022 0002 …">${esc(c?.code ?? "")}</textarea></label>
      <div class="info" id="cinfo"></div>
      <div class="wave" id="cwave" aria-label="IR waveform preview"></div>
      <div class="two">
        <label class="f">Repeat (blank = use code's own)<input id="crep" type="number" min="1" max="50" placeholder="auto" value="${esc(c?.repeat ?? "")}"></label>
        <div></div>
      </div>
      <p class="hint">Paste a Global Caché <b>sendir</b> code, bare GC data, or a <b>Pronto hex</b> code (e.g. from the Global Caché Control Tower database or irdb). Or hit <b>Learn</b> and point your remote at the iTach.</p>
      <div class="actions">
        <button class="btn" id="clearn">📡 Learn</button>
        <button class="btn" id="ctest">▶ Test</button>
        <button class="btn ghost" id="cconv" hidden title="Rewrite as a Global Caché sendir string">⇄ Convert to sendir</button>
        <span class="spacer"></span>
        ${c ? `<button class="btn danger" id="cdel">🗑</button>` : ""}
        <button class="btn" data-a="close">Cancel</button>
        <button class="btn primary" id="csave">Save</button></div>`);

    const $ = (s) => m.querySelector(s);
    const codeEl = $("#ccode");
    let parsed = null;
    let parseT;
    const update = async () => {
      const code = codeEl.value.trim();
      const info = $("#cinfo"), wave = $("#cwave");
      if (!code) { parsed = null; info.innerHTML = ""; wave.innerHTML = this._waveEmpty("Waveform preview shows up here"); $("#cconv").hidden = true; return; }
      try {
        parsed = await this.ws("parse", { code });
        if (codeEl.value.trim() !== code) return; // stale
        const dur = parsed.pulses ? parsed.pulses.reduce((s, p) => s + p, 0) / parsed.freq * 1000 : null;
        info.innerHTML = `<span class="badge ok">✓ ${esc(FORMAT_LABEL[parsed.format] || parsed.format)}</span>
          <span class="m">${(parsed.freq / 1000).toFixed(1)} kHz · ${parsed.pulse_count / (parsed.pulses ? 2 : 1)} ${parsed.pulses ? "pulse pairs" : "tokens"}${dur ? ` · ${dur.toFixed(0)} ms` : ""} · repeat ${parsed.repeat}</span>`;
        wave.innerHTML = parsed.pulses ? this._wave(parsed) : this._waveEmpty("No preview for compressed codes");
        $("#cconv").hidden = parsed.format === "sendir";
      } catch (e) {
        if (codeEl.value.trim() !== code) return;
        parsed = null;
        info.innerHTML = `<span class="badge bad">✗ ${esc(errMsg(e))}</span>`;
        wave.innerHTML = this._waveEmpty("");
        $("#cconv").hidden = true;
      }
    };
    codeEl.addEventListener("input", () => { clearTimeout(parseT); parseT = setTimeout(update, 250); });
    update();

    const repeat = () => { const v = $("#crep").value.trim(); return v ? parseInt(v, 10) : null; };

    $("#cconv").onclick = () => { if (parsed) { codeEl.value = parsed.sendir.replace(/^sendir,[^,]+,/, `sendir,${dev.connector},`); update(); } };

    $("#ctest").onclick = async () => {
      const btn = $("#ctest");
      btn.disabled = true;
      try {
        await this.ws("send", { entry_id: this._entryId, code: codeEl.value, connector: dev.connector, repeat: repeat() });
        this._toast("Sent! Did it work? 👀");
      } catch (e) { this._toast(errMsg(e), true); } finally { btn.disabled = false; }
    };

    const learn = async () => {
      const btn = $("#clearn"), box = $("#learnbox");
      btn.disabled = true;
      this._learnAbort = false;
      let left = 15;
      box.innerHTML = `<div class="learn"><div class="pulse"></div><div>Listening… point your remote at the iTach and press the button once. <b id="lcount">${left}s</b></div></div>`;
      const timer = setInterval(() => { left = Math.max(0, left - 1); const lc = box.querySelector("#lcount"); if (lc) lc.textContent = `${left}s`; }, 1000);
      try {
        const res = await this.ws("learn", { entry_id: this._entryId, timeout: 15 });
        if (this._learnAbort) return;
        codeEl.value = res.code;
        await update();
        this._toast("Got it! 🎉 Hit Test to check it");
        if (!$("#cname").value.trim()) $("#cname").focus();
      } catch (e) { if (!this._learnAbort) this._toast(errMsg(e), true); }
      finally { clearInterval(timer); if (box.isConnected) box.innerHTML = ""; btn.disabled = false; }
    };
    $("#clearn").onclick = learn;

    $("#csave").onclick = async () => {
      const btn = $("#csave");
      btn.disabled = true;
      try {
        await this.ws("command/save", {
          entry_id: this._entryId, device_id: this._selDev, command_id: cmdId,
          name: $("#cname").value, code: codeEl.value, repeat: repeat(),
        });
        this._closeModal();
        await this._reload();
        this._toast(c ? "Code saved 💾" : "Code added – it's also a button entity now 🎉");
      } catch (e) { this._toast(errMsg(e), true); btn.disabled = false; }
    };
    const del = $("#cdel");
    if (del) del.onclick = async () => {
      if (!confirm(`Delete “${c.name}”? Its button entity goes too.`)) return;
      try {
        await this.ws("command/delete", { entry_id: this._entryId, device_id: this._selDev, command_id: cmdId });
        this._closeModal();
        await this._reload();
        this._toast("Code deleted");
      } catch (e) { this._toast(errMsg(e), true); }
    };
    if (autoLearn) learn();
  }

  _waveEmpty(text) {
    return `<span class="wempty">${esc(text)}</span>`;
  }

  _wave(p) {
    // pulses are carrier-cycle counts: on, off, on, off…
    const W = 1000, H = 64, top = 14, bot = 52;
    const total = p.pulses.reduce((s, x) => s + x, 0) || 1;
    const sx = W / total;
    let x = 0, d = `M0 ${bot}`;
    let repX = null;
    p.pulses.forEach((len, i) => {
      if (i === p.offset - 1) repX = x * sx;
      const y = i % 2 === 0 ? top : bot;
      d += ` L${(x * sx).toFixed(2)} ${y} L${((x + len) * sx).toFixed(2)} ${y}`;
      x += len;
    });
    d += ` L${W} ${bot}`;
    const rep = repX !== null && p.offset > 1
      ? `<rect class="rep" x="${repX.toFixed(1)}" y="0" width="${(W - repX).toFixed(1)}" height="${H}"/>` : "";
    return `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">${rep}<path class="sig" d="${d}"/></svg>`;
  }

  // ---------- import / export ----------
  async _export() {
    const data = await this.ws("export", { entry_id: this._entryId });
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `itach-codes-${(this._entry?.title || "export").replace(/[^\w-]+/g, "_")}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
    this._toast("Exported ⬇");
  }

  _importDialog() {
    const m = this._openModal(`<h3>Import codes</h3>
      <p class="hint" style="margin:0 0 14px">Paste an export from this panel, or a simple JSON like <code>{"TV": {"Power": "sendir,…", "Mute": "0000 006D …"}}</code>.</p>
      <label class="f">Pick a file<input type="file" id="ifile" accept=".json,application/json"></label>
      <label class="f">…or paste JSON<textarea id="itext" spellcheck="false"></textarea></label>
      <label class="chk"><input type="checkbox" id="irep"> Replace everything (otherwise merges by name)</label>
      <div class="actions"><span class="spacer"></span><button class="btn" data-a="close">Cancel</button><button class="btn primary" id="igo">Import</button></div>`);
    m.querySelector("#ifile").onchange = async (e) => {
      const f = e.target.files?.[0];
      if (f) m.querySelector("#itext").value = await f.text();
    };
    m.querySelector("#igo").onclick = async () => {
      let data;
      try { data = JSON.parse(m.querySelector("#itext").value); }
      catch (e) { this._toast("That isn't valid JSON 😕", true); return; }
      const replace = m.querySelector("#irep").checked;
      if (replace && !confirm("Replace ALL devices and codes on this iTach?")) return;
      try {
        const res = await this.ws("import", { entry_id: this._entryId, data, replace });
        this._closeModal();
        await this._reload();
        this._toast(`Imported ${res.commands} codes across ${res.devices} devices 🎉`);
      } catch (e) { this._toast(errMsg(e), true); }
    };
  }
}

if (!customElements.get("itach-gc-panel")) customElements.define("itach-gc-panel", ItachGcPanel);
