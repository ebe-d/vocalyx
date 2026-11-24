/* ══════════════════════════════════════════════════════════════════
   VOCALYX — Frontend Application
   ══════════════════════════════════════════════════════════════════ */

'use strict';

/* ─── Backend URL Configuration ─────────────────────────────────── */
const LS_KEY = 'vocalyx_backend_url';
const DEFAULT_BACKEND_URL = 'https://ebedsouza-vocalyx.hf.space';

const api = {
  base: localStorage.getItem(LS_KEY) || DEFAULT_BACKEND_URL,

  async _fetch(method, path, body = null, isFormData = false, timeoutMs = 60000) {
    if (!api.base && !path.startsWith('http')) {
      throw new Error('No backend URL configured. Go to Settings to connect.');
    }
    const url = api.base ? (api.base.replace(/\/$/, '') + path) : path;
    const baseHeaders = { 'ngrok-skip-browser-warning': 'true' };
    const opts = {
      method,
      signal: AbortSignal.timeout(timeoutMs),
      headers: isFormData
        ? baseHeaders
        : { ...baseHeaders, 'Content-Type': 'application/json' },
    };
    if (body) opts.body = isFormData ? body : JSON.stringify(body);
    const res = await fetch(url, opts);
    if (!res.ok) {
      let msg = `HTTP ${res.status}`;
      try { const e = await res.json(); msg = e.detail || e.message || msg; } catch {}
      throw new Error(msg);
    }
    const ct = res.headers.get('content-type') || '';
    return ct.includes('application/json') ? res.json() : res.text();
  },

  get:      (path)       => api._fetch('GET',    path),
  post:     (path, body, timeoutMs = 60000) => api._fetch('POST', path, body, false, timeoutMs),
  delete:   (path)       => api._fetch('DELETE', path),
  patch:    (path, body, timeoutMs = 60000) => api._fetch('PATCH', path, body, false, timeoutMs),
  postForm: (path, fd, timeoutMs = 60000)   => api._fetch('POST', path, fd, true, timeoutMs),

  getCalls:       ()     => api.get('/api/calls'),
  getContacts:    ()     => api.get('/api/contacts'),
  getScripts:     ()     => api.get('/api/scripts'),
  createScript:   (d)    => api.post('/api/scripts', d),
  deleteScript:   (id)   => api.delete(`/api/scripts/${id}`),
  updateContact:  (id, d)=> api.patch(`/api/contacts/${id}`, d),
  getDashboardStats:()   => api.get('/api/dashboard/stats'),
  getDocuments:   ()     => api.get('/api/documents'),
  getHealth:      ()     => api.get('/api/health'),
  createContact:  (d)    => api.post('/api/contacts', d),
  deleteContact:  (id)   => api.delete(`/api/contacts/${id}`),
  deleteDocument: (id)   => api.delete(`/api/documents/${id}`),
  uploadDocument: (fd)   => api.postForm('/api/documents', fd),
  chat:           (d)    => api.post('/api/chat', d),
  synthesize:     (text, engine = 'f5tts') => api.post('/api/tts', { text, engine }, 60000),
  analyzeCall:    (d)    => api.post('/api/calls/analyze', d),
  cloneVoice:     (fd)   => api.postForm('/api/clone-voice', fd, 120000),
  getVoiceStatus: ()     => api.get('/api/voice/status'),
  testVoiceActive:(exag, cfg) => api.post(`/api/voice/test?exaggeration=${exag}&cfg_weight=${cfg}`, {}, 120000),
  getTwilioConfig:()     => api.get('/api/twilio/config'),
  updateTwilioConfig:(d) => api.post('/api/twilio/config', d),
  testTwilio:     ()     => api.post('/api/twilio/test'),
  dialPhone:      (d)    => api.post('/api/twilio/call', d, 30000),
  hangupPhone:    (call_sid) => api.post('/api/twilio/hangup', { call_sid }),
  getActivePhoneCall:(call_sid) => api.get(`/api/twilio/active-call${call_sid ? '?call_sid=' + call_sid : ''}`),
  getAlertsConfig:   ()     => api.get('/api/alerts/config'),
  updateAlertsConfig:(d)    => api.post('/api/alerts/config', d),
  testAlert:         (d)    => api.post('/api/alerts/test', d),
  getPrewarmStatus:  ()     => api.get('/api/tts/prewarm-status'),
  prewarmVoice:   (engine = null, voiceId = null) => {
    const params = new URLSearchParams();
    if (engine) params.set('engine', engine);
    if (voiceId) params.set('voice_id', voiceId);
    const qs = params.toString();
    return api._fetch('POST', qs ? `/api/tts/prewarm?${qs}` : '/api/tts/prewarm', {}, false, 120000);
  },
  getVoices:      ()     => api.get('/api/voices'),
  computeVoice:   (fd)   => api.postForm('/api/voices/compute', fd, 180000),
  saveVoice:      (d)    => api.post('/api/voices', d),
  activateVoice:  (id)   => api.post(`/api/voices/${id}/activate`),
  deleteVoice:    (id)   => api.delete(`/api/voices/${id}`),
};

/* ─── Utility Helpers ───────────────────────────────────────────── */
function formatDate(iso) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: 'short', day: 'numeric', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  } catch { return iso; }
}

function scoreBadge(score) {
  if (score === null || score === undefined) return `<span class="badge badge-grey">N/A</span>`;
  const n = Number(score);
  if (n >= 70) return `<span class="badge badge-lime">🔥 ${n}</span>`;
  if (n >= 40) return `<span class="badge badge-yellow">⚡ ${n}</span>`;
  return `<span class="badge badge-red">❄️ ${n}</span>`;
}

function sentimentBadge(s) {
  if (!s) return `<span class="badge badge-grey">—</span>`;
  const map = { positive: 'badge-green', neutral: 'badge-grey', negative: 'badge-red' };
  const cls = map[s.toLowerCase()] || 'badge-grey';
  return `<span class="badge ${cls}">${s}</span>`;
}

function outcomeBadge(o) {
  if (!o) return `<span class="badge badge-grey">—</span>`;
  const map = {
    'interested':         'badge-green',
    'not interested':     'badge-red',
    'requested callback': 'badge-blue',
    'time-waster':        'badge-red',
    'needs follow-up':    'badge-yellow',
  };
  const cls = map[o.toLowerCase()] || 'badge-grey';
  return `<span class="badge ${cls}">${o}</span>`;
}

/* ─── Post-Call Multi-Channel Alert Status Renderer ──────────────── */
function renderAlertStatusRows(analysis, prefix = 'phone') {
  if (!analysis) return;
  const alertsRes = analysis.alerts_result || {};
  const cfg = (typeof alertsManager !== 'undefined' && alertsManager.config) ? alertsManager.config : {};

  // 1. WhatsApp Alert Row
  const waRow = document.getElementById(prefix === 'phone' ? 'phone-whatsapp-row' : 'sim-whatsapp-row');
  const waBadge = document.getElementById(prefix === 'phone' ? 'phone-whatsapp-badge' : 'sim-whatsapp-badge');
  const waSent = Boolean(analysis.whatsapp_sent || alertsRes.whatsapp?.ok);
  const waAttempted = Boolean(alertsRes.whatsapp);
  if (waRow) {
    waRow.style.display = 'flex';
    if (waBadge) {
      if (waSent) {
        waBadge.className = 'badge badge-lime';
        waBadge.innerHTML = '<i data-lucide="check-circle" style="width:12px;height:12px;"></i> ✓ WhatsApp Sent';
      } else if (waAttempted && alertsRes.whatsapp.enabled === false) {
        waBadge.className = 'badge badge-gray';
        waBadge.textContent = 'Disabled';
      } else if (waAttempted && alertsRes.whatsapp.message) {
        waBadge.className = 'badge badge-red';
        waBadge.title = alertsRes.whatsapp.message;
        waBadge.innerHTML = '<i data-lucide="alert-circle" style="width:12px;height:12px;"></i> Not Sent';
      } else {
        waBadge.className = 'badge badge-gray';
        waBadge.innerHTML = '<i data-lucide="clock" style="width:12px;height:12px;"></i> Active';
      }
    }
  }

  // 2. Telegram Alert Row
  const tgRow = document.getElementById(prefix === 'phone' ? 'phone-telegram-row' : 'telegram-row');
  const tgBadge = document.getElementById(prefix === 'phone' ? 'phone-telegram-badge' : 'sim-telegram-badge');
  const tgSent = Boolean(analysis.telegram_sent || alertsRes.telegram?.ok);
  if (tgRow) {
    tgRow.style.display = 'flex';
    if (tgBadge) {
      if (tgSent) {
        tgBadge.className = 'badge badge-lime';
        tgBadge.innerHTML = '<i data-lucide="send" style="width:12px;height:12px;"></i> ✓ Telegram Sent';
      } else {
        tgBadge.className = 'badge badge-gray';
        tgBadge.innerHTML = '<i data-lucide="clock" style="width:12px;height:12px;"></i> Active';
      }
    }
  }

  // 3. SMS Alert Row
  const smsRow = document.getElementById(prefix === 'phone' ? 'phone-sms-row' : 'sim-sms-row');
  const smsBadge = document.getElementById(prefix === 'phone' ? 'phone-sms-badge' : 'sim-sms-badge');
  const smsSent = Boolean(analysis.sms_sent || alertsRes.sms?.ok);
  const smsAttempted = Boolean(alertsRes.sms);
  if (smsRow) {
    if (smsSent || (cfg.sms && cfg.sms.enabled)) {
      smsRow.style.display = 'flex';
      if (smsBadge) {
        if (smsSent) {
          smsBadge.className = 'badge badge-lime';
          smsBadge.innerHTML = '<i data-lucide="phone" style="width:12px;height:12px;"></i> ✓ SMS Sent';
        } else {
          smsBadge.className = 'badge badge-gray';
          smsBadge.innerHTML = '<i data-lucide="clock" style="width:12px;height:12px;"></i> SMS Ready';
        }
      }
    } else {
      smsRow.style.display = 'none';
    }
  }

  if (typeof lucide !== 'undefined' && lucide.createIcons) {
    lucide.createIcons();
  }
}

/* ─── Bidirectional Language & Voice Engine Synchronizer ─────────── */
const languageEngineSync = {
  syncFromEngine(engineVal, langSelectEl) {
    if (!langSelectEl || !engineVal) return;
    const ev = engineVal.toLowerCase();
    const isCloned = ['f5tts', 'luxtts'].includes(ev);
    const isKannada = ev.includes('kannada') || ev.includes('kn');
    const isHindi = ev.includes('hindi') || ev.includes('hi');

    Array.from(langSelectEl.options).forEach(opt => {
      const v = opt.value;
      // Store original text ONCE — never read it back from modified text
      if (!opt.dataset.origText) opt.dataset.origText = opt.text;
      // Always restore first, then set disabled state only (no text modification)
      opt.text = opt.dataset.origText;
      if (isCloned) {
        opt.disabled = (v === 'kn-IN' || v === 'hi-IN');
      } else if (isKannada) {
        opt.disabled = (v !== 'kn-IN');
      } else if (isHindi) {
        opt.disabled = (v !== 'hi-IN');
      } else {
        opt.disabled = false;
      }
    });

    const currentOpt = langSelectEl.selectedOptions ? langSelectEl.selectedOptions[0] : null;
    if (isCloned && currentOpt && currentOpt.disabled) {
      langSelectEl.value = 'en-US';
      toast.info('Cloned voices (F5-TTS/LuxTTS) support English only. Language set to English (US).');
    } else if (isKannada && langSelectEl.value !== 'kn-IN') {
      langSelectEl.value = 'kn-IN';
      toast.info('Sapna/Gagan voice active: Language set to Kannada (ಕನ್ನಡ).');
    } else if (isHindi && langSelectEl.value !== 'hi-IN') {
      langSelectEl.value = 'hi-IN';
      toast.info('Swara/Madhur voice active: Language set to Hindi (हिंदी).');
    }
  },

  syncFromLanguage(langVal, engineSelectEl) {
    if (!engineSelectEl || !langVal) return;
    const isKn = (langVal === 'kn-IN' || langVal === 'kn');
    const isHi = (langVal === 'hi-IN' || langVal === 'hi');
    const isEn = (langVal === 'en-US' || langVal === 'en-IN' || !langVal);

    Array.from(engineSelectEl.options).forEach(opt => {
      const ev = opt.value.toLowerCase();
      const isKannadaVoice = ev.includes('kannada') || ev.includes('kn');
      const isHindiVoice = ev.includes('hindi') || ev.includes('hi');

      // Store original text ONCE — always restore it, never append "not supported" to opt.text
      if (!opt.dataset.origText) opt.dataset.origText = opt.text;
      opt.text = opt.dataset.origText;

      if (isKn) {
        opt.disabled = !isKannadaVoice;
      } else if (isHi) {
        opt.disabled = !isHindiVoice;
      } else {
        // English: disable Indic-only voices
        opt.disabled = (isKannadaVoice || isHindiVoice);
      }
    });

    if (isKn) {
      if (!engineSelectEl.value.includes('kannada')) {
        const knOpt = Array.from(engineSelectEl.options).find(o => o.value.includes('kannada') && !o.disabled);
        engineSelectEl.value = knOpt ? knOpt.value : 'kannada_female';
        toast.info('Kannada selected: Voice engine set to Sapna (Studio Neural).');
      }
    } else if (isHi) {
      if (!engineSelectEl.value.includes('hindi')) {
        const hiOpt = Array.from(engineSelectEl.options).find(o => o.value.includes('hindi') && !o.disabled);
        engineSelectEl.value = hiOpt ? hiOpt.value : 'hindi_female';
        toast.info('Hindi selected: Voice engine set to Swara (Studio Neural).');
      }
    } else if (isEn) {
      const ev = engineSelectEl.value.toLowerCase();
      if (ev.includes('kannada') || ev.includes('hindi')) {
        const activeEn = Array.from(engineSelectEl.options).find(o => !o.disabled);
        engineSelectEl.value = activeEn ? activeEn.value : 'f5tts';
      }
    }

    const badgeId = engineSelectEl.id === 'phone-tts-engine' ? 'phone-tts-badge' : 'sim-tts-badge';
    const badge = document.getElementById(badgeId);
    const selectedOpt = engineSelectEl.selectedOptions?.[0];
    if (badge && engineSelectEl.value) {
      const curVal = engineSelectEl.value.toUpperCase();
      badge.textContent = `${curVal} Active`;
    }
    if (engineSelectEl.id === 'sim-tts-engine' && selectedOpt) {
      const modelTag = document.getElementById('sim-model-tag');
      if (modelTag) {
        const shortName = (selectedOpt.textContent || '').split('—')[0].trim() || engineSelectEl.value.toUpperCase();
        modelTag.innerHTML = `<i data-lucide="cpu"></i> Groq LLaMA / ${escapeHtml(shortName)}`;
        lucide.createIcons({ nodes: [modelTag] });
      }
    }
  }
};

function interestBadge(lvl) {
  const map = { high: 'badge-lime', medium: 'badge-yellow', low: 'badge-red' };
  const cls = map[(lvl || '').toLowerCase()] || 'badge-grey';
  return `<span class="badge ${cls}">${lvl || 'Unknown'}</span>`;
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function extractWords(str) {
  if (!str) return [];
  const matches = String(str).match(/\b[a-zA-Z0-9]{2,}\b/g);
  if (!matches) return [];
  const words = matches.map(w => w.toLowerCase());
  // Filter out single throat-clearing/breath filler sounds
  if (words.length === 1 && ['uh', 'um', 'ah', 'eh', 'mm', 'hmm'].includes(words[0])) {
    return [];
  }
  return words;
}

/* ─── Toast Notifications ───────────────────────────────────────── */
const toast = (() => {
  const container = document.getElementById('toast-container');
  function show(msg, type = 'info', duration = 3000) {
    const icons = { success: 'check-circle', error: 'x-circle', info: 'info' };
    const el = document.createElement('div');
    el.className = `toast toast-${type}`;
    el.innerHTML = `<i data-lucide="${icons[type] || 'info'}"></i><span>${escapeHtml(msg)}</span>`;
    container.appendChild(el);
    lucide.createIcons({ nodes: [el] });
    setTimeout(() => el.remove(), duration + 400);
  }
  return {
    success: (m) => show(m, 'success'),
    error:   (m) => show(m, 'error', 4500),
    info:    (m) => show(m, 'info'),
  };
})();

/* ─── UI State ──────────────────────────────────────────────────── */
const state = {
  currentSection: 'dashboard',
  selectedLanguage: localStorage.getItem('vocalyx_language') || 'en-US',
  contacts:       [],
  calls:          [],
  scripts:        [],
  docs:           [],
  callActive:     false,
  callMode:       'outbound',  // 'outbound' | 'inbound' | 'marketing'
  recognition:    null,
  silenceTimer:   null,
  activeSpeech:   '',
  chatRequestId:  0,
  transcript:     [],
  currentContact: null,
  timerInterval:  null,
  timerSeconds:   0,
  voiceFile:      null,
  voiceStatus:    { has_voice_clone: false, filename: null, size_kb: 0 },
  backendOk:      false,
  isSpeaking:     false,
  currentAudio:   null,
  currentSpeakingText: null,
  twilioConfig:       { configured: false, account_sid: '', phone_number: '', webhook_url: '' },
  activeTwilioCall:   null,
  twilioPollInterval: null,
  twilioTimerInterval:null,
  twilioTimerSeconds: 0,
};

/* ─── Backend Status ────────────────────────────────────────────── */
function updateStatusUI(connected, label) {
  const dot   = document.getElementById('status-dot');
  const lbl   = document.getElementById('status-label');
  const cDot  = document.getElementById('conn-dot');
  const cLbl  = document.getElementById('conn-label');

  dot.className  = 'status-dot ' + (connected ? 'online' : 'offline');
  lbl.textContent = label || (connected ? 'Connected' : 'Not connected');

  if (cDot) cDot.className = 'conn-dot ' + (connected ? 'connected' : 'disconnected');
  if (cLbl) cLbl.textContent = label || (connected ? 'Connected' : 'Disconnected');

  state.backendOk = connected;
  const banner = document.getElementById('backend-banner');
  if (banner) banner.style.display = connected ? 'none' : 'flex';
}

async function checkBackendHealth(url) {
  if (!url) { updateStatusUI(false); return false; }
  try {
    const base = url.replace(/\/$/, '');
    const res = await fetch(base + '/api/health', {
      signal: AbortSignal.timeout(5000),
      headers: { 'ngrok-skip-browser-warning': 'true' },
    });
    if (res.ok) {
      const data = await res.json().catch(() => ({}));
      updateStatusUI(true, 'Connected');
      if (data.voice_clone) {
        state.voiceStatus = data.voice_clone;
        if (typeof simulator !== 'undefined' && simulator.updateVoiceBadge) {
          simulator.updateVoiceBadge();
        }
      }
      if (typeof twilioManager !== 'undefined' && twilioManager.loadConfig) {
        twilioManager.loadConfig();
      }
      if (typeof voicePrewarmManager !== 'undefined' && voicePrewarmManager.checkStatus) {
        voicePrewarmManager.checkStatus();
      }
      if (typeof voicesManager !== 'undefined' && voicesManager.loadVoices) {
        voicesManager.loadVoices();
      }
      // Show health info
      const hi = document.getElementById('health-info');
      if (hi) {
        hi.style.display = 'block';
        document.getElementById('health-model').textContent    = data.model    || '—';
        document.getElementById('health-tts').textContent      = data.tts      || '—';
        document.getElementById('health-docs').textContent     = data.rag_docs !== undefined ? data.rag_docs : '—';
        document.getElementById('health-telegram').textContent = data.telegram ? '✓ Connected' : '✗ Not configured';
      }
      return true;
    }
  } catch {}
  updateStatusUI(false, 'Disconnected');
  return false;
}

/* ─── Navigation ────────────────────────────────────────────────── */
const ui = {

  showSection(name) {
    state.currentSection = name;

    document.querySelectorAll('.nav-item').forEach(el => {
      el.classList.toggle('active', el.dataset.section === name);
    });
    document.querySelectorAll('.section').forEach(el => {
      el.classList.toggle('active', el.id === `section-${name}`);
    });

    const labels = {
      dashboard: 'Dashboard',
      'phone-call': 'Real Phone Call (Twilio)',
      simulator: 'Call Simulator',
      contacts:  'Contacts',
      knowledge: 'Knowledge Base',
      voices:    'Voices Library',
      voice:     'Voices Library',
      history:   'Call History',
      scripts:   'Call Scripts',
      alerts:    'Message Alerts',
      settings:  'Settings',
    };
    document.getElementById('breadcrumb').textContent = labels[name] || name;

    const loaders = {
      dashboard: ui.loadDashboard,
      'phone-call': () => {
        ui.loadSimulatorContacts();
        twilioManager.loadConfig();
        voicePrewarmManager.checkStatus();
      },
      contacts:  ui.loadContacts,
      knowledge: ui.loadDocuments,
      history:   ui.loadHistory,
      scripts:   ui.loadScripts,
      alerts:    () => alertsManager.loadConfig(),
      simulator: () => {
        ui.loadSimulatorContacts();
        ui.loadScripts();
      },
      settings:  ui.loadSettings,
      voices:    () => voicesManager.loadVoices(),
      voice:     () => voicesManager.loadVoices(),
    };
    if (loaders[name]) loaders[name]();
  },

  /* ── Dashboard ──────────────────────────────────────────────── */
  async loadDashboard() {
    try {
      const [stats, calls, contacts] = await Promise.all([
        api.getDashboardStats().catch(() => null),
        api.getCalls(),
        api.getContacts(),
      ]);
      state.calls    = calls    || [];
      state.contacts = contacts || [];

      if (stats && stats.total_calls !== undefined) {
        document.getElementById('stat-total-calls').textContent    = stats.total_calls;
        document.getElementById('stat-total-contacts').textContent  = stats.total_contacts;
        document.getElementById('stat-avg-lead-score').textContent  = stats.total_calls ? stats.avg_lead_score : '—';
        document.getElementById('stat-hot-leads').textContent       = stats.hot_leads;
        ui._fillCallTable('hot-leads-tbody', stats.recent_hot_leads || []);
        ui._fillCallTable('recent-calls-tbody', stats.recent_calls || []);
      } else {
        const hotLeads = state.calls.filter(c => (c.lead_score || 0) >= 70);
        const avgScore = state.calls.length
          ? Math.round(state.calls.reduce((s, c) => s + (c.lead_score || 0), 0) / state.calls.length)
          : 0;

        document.getElementById('stat-total-calls').textContent    = state.calls.length;
        document.getElementById('stat-total-contacts').textContent  = state.contacts.length;
        document.getElementById('stat-avg-lead-score').textContent  = state.calls.length ? avgScore : '—';
        document.getElementById('stat-hot-leads').textContent       = hotLeads.length;

        const hotRecent = [...hotLeads]
          .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
          .slice(0, 5);
        ui._fillCallTable('hot-leads-tbody', hotRecent);

        const recent = [...state.calls]
          .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
          .slice(0, 5);
        ui._fillCallTable('recent-calls-tbody', recent);
      }
    } catch (e) {
      toast.error(`Dashboard: ${e.message}`);
    }
  },

  _fillCallTable(tbodyId, rows) {
    const tbody = document.getElementById(tbodyId);
    if (!tbody) return;
    const contactMap = Object.fromEntries(state.contacts.map(c => [c.id, c.name]));
    if (!rows.length) {
      tbody.innerHTML = `<tr><td colspan="5" class="empty-row">No data yet</td></tr>`;
      return;
    }
    tbody.innerHTML = rows.map(c => `
      <tr>
        <td>${escapeHtml(c.contact_name || contactMap[c.contact_id] || `#${c.contact_id}`)}</td>
        <td>${scoreBadge(c.lead_score)}</td>
        <td>${sentimentBadge(c.sentiment)}</td>
        <td>${outcomeBadge(c.outcome)}</td>
        <td style="font-size:0.75rem;color:var(--text-muted)">${formatDate(c.created_at)}</td>
      </tr>
    `).join('');
  },

  /* ── Simulator & Phone Contacts ──────────────────────────────── */
  async loadSimulatorContacts() {
    try {
      const contacts = await api.getContacts();
      state.contacts = contacts || [];
      const selIds = ['contact-select', 'contact-select-mkt', 'phone-contact-select'];
      selIds.forEach(id => {
        const sel = document.getElementById(id);
        if (!sel) return;
        sel.innerHTML = `<option value="">— Choose a contact —</option>` +
          contacts.map(c => `<option value="${c.id}">${escapeHtml(c.name)} — ${escapeHtml(c.phone_number || '')}</option>`).join('');
      });
    } catch (e) {
      toast.error(`Could not load contacts: ${e.message}`);
    }
  },

  /* ── Contacts ───────────────────────────────────────────────── */
  async loadContacts() {
    const grid = document.getElementById('contacts-grid');
    grid.innerHTML = `<div class="loading-state"><div class="spinner"></div><p>Loading contacts…</p></div>`;
    try {
      state.contacts = (await api.getContacts()) || [];
      ui._renderContacts();
    } catch (e) {
      grid.innerHTML = `<div class="loading-state" style="color:var(--red)">${escapeHtml(e.message)}</div>`;
      toast.error(`Load contacts: ${e.message}`);
    }
  },

  _renderContacts() {
    const grid = document.getElementById('contacts-grid');
    if (!state.contacts.length) {
      grid.innerHTML = `<div class="loading-state" style="grid-column:1/-1"><p>No contacts yet. Add your first contact!</p></div>`;
      return;
    }
    grid.innerHTML = state.contacts.map(c => `
      <div class="contact-card" data-id="${c.id}">
        <div class="contact-card-header">
          <div>
            <div class="contact-name">${escapeHtml(c.name)}</div>
            <div class="contact-phone"><i data-lucide="phone"></i> ${escapeHtml(c.phone_number || '—')}</div>
          </div>
          <div style="display:flex; gap:6px; align-items:center;">
            ${c.preferred_language && c.preferred_language !== 'en-US' ? `<span class="badge" style="font-size:0.65rem; background:rgba(99,102,241,0.15); color:#818cf8; border:1px solid rgba(99,102,241,0.3); text-transform:uppercase;">${escapeHtml(c.preferred_language)}</span>` : ''}
            ${interestBadge(c.interest_level)}
          </div>
        </div>
        <div class="contact-meta">
          ${c.last_topic  ? `<div class="contact-meta-row"><span class="contact-meta-label">Last Topic</span><span class="contact-meta-value">${escapeHtml(c.last_topic)}</span></div>` : ''}
          ${c.concerns    ? `<div class="contact-meta-row"><span class="contact-meta-label">Concerns</span><span class="contact-meta-value">${escapeHtml(c.concerns)}</span></div>` : ''}
          ${c.commitments ? `<div class="contact-meta-row"><span class="contact-meta-label">Commitments</span><span class="contact-meta-value">${escapeHtml(c.commitments)}</span></div>` : ''}
          ${c.notes       ? `<div class="contact-meta-row"><span class="contact-meta-label">Notes</span><span class="contact-meta-value">${escapeHtml(c.notes)}</span></div>` : ''}
        </div>
        <div class="contact-actions">
          <button class="btn btn-outline btn-sm btn-edit-contact" data-id="${c.id}" title="Edit contact details and memory">
            <i data-lucide="edit-3"></i> Edit
          </button>
          <button class="btn btn-lime btn-sm btn-call-contact" data-id="${c.id}" title="Call in Browser">
            <i data-lucide="phone-call"></i> Browser
          </button>
          <button class="btn btn-dark btn-sm btn-dial-contact" data-id="${c.id}" data-phone="${escapeHtml(c.phone_number || '')}" title="Call Actual Phone via Twilio">
            <i data-lucide="phone-outgoing"></i> Real Phone
          </button>
          <button class="btn-delete btn-delete-contact" data-id="${c.id}">
            <i data-lucide="trash-2"></i>
          </button>
        </div>
      </div>
    `).join('');
    lucide.createIcons({ nodes: [grid] });

    grid.querySelectorAll('.btn-edit-contact').forEach(btn => {
      btn.addEventListener('click', () => {
        const c = state.contacts.find(x => x.id == btn.dataset.id);
        if (!c) return;
        document.getElementById('edit-contact-id').value = c.id;
        document.getElementById('edit-contact-name').value = c.name || '';
        document.getElementById('edit-contact-phone').value = c.phone_number || '';
        document.getElementById('edit-contact-language').value = c.preferred_language || 'en-US';
        document.getElementById('edit-contact-interest').value = c.interest_level || 'Unknown';
        document.getElementById('edit-contact-topic').value = c.last_topic || '';
        document.getElementById('edit-contact-concerns').value = c.concerns || '';
        document.getElementById('edit-contact-commitments').value = c.commitments || '';
        document.getElementById('edit-contact-notes').value = c.notes || '';
        document.getElementById('modal-contact-edit').style.display = 'flex';
      });
    });

    grid.querySelectorAll('.btn-call-contact').forEach(btn => {
      btn.addEventListener('click', () => {
        ui.showSection('simulator');
        setTimeout(() => {
          document.getElementById('contact-select').value = btn.dataset.id;
          // Switch to outbound mode
          document.querySelector('.mode-tab[data-mode="outbound"]')?.click();
        }, 100);
      });
    });

    grid.querySelectorAll('.btn-dial-contact').forEach(btn => {
      btn.addEventListener('click', () => {
        const phone = btn.dataset.phone;
        ui.showSection('phone-call');
        setTimeout(() => {
          const sel = document.getElementById('phone-contact-select');
          if (sel) sel.value = btn.dataset.id;
          const phoneInp = document.getElementById('twilio-dial-number');
          if (phoneInp && phone) phoneInp.value = phone;
          toast.info(`Ready to call ${phone} via Twilio. Click "Call Real Phone" to dial.`);
        }, 150);
      });
    });

    grid.querySelectorAll('.btn-delete-contact').forEach(btn => {
      btn.addEventListener('click', () => simulator.deleteContact(btn.dataset.id));
    });
  },

  /* ── Knowledge Base ─────────────────────────────────────────── */
  async loadDocuments() {
    const list = document.getElementById('doc-list');
    list.innerHTML = `<div class="loading-state"><div class="spinner"></div><p>Loading…</p></div>`;
    try {
      state.docs = (await api.getDocuments()) || [];
      ui._renderDocuments();
    } catch (e) {
      list.innerHTML = `<div class="loading-state" style="color:var(--red)">${escapeHtml(e.message)}</div>`;
    }
  },

  _renderDocuments() {
    const list = document.getElementById('doc-list');
    document.getElementById('doc-count').textContent = `${state.docs.length} doc${state.docs.length !== 1 ? 's' : ''}`;
    if (!state.docs.length) {
      list.innerHTML = `<div class="loading-state"><p style="color:var(--text-muted)">No documents indexed yet. Upload a file above.</p></div>`;
      return;
    }
    list.innerHTML = state.docs.map(d => `
      <div class="doc-item" data-id="${d.id}">
        <div class="doc-item-icon"><i data-lucide="file-text"></i></div>
        <div class="doc-item-info">
          <div class="doc-item-name">${escapeHtml(d.filename)}</div>
          <div class="doc-item-date">${formatDate(d.uploaded_at)}</div>
        </div>
        <div class="doc-item-actions">
          <span class="badge badge-lime">✓ Indexed</span>
          <button class="btn-delete btn-delete-doc" data-id="${d.id}">
            <i data-lucide="trash-2"></i>
          </button>
        </div>
      </div>
    `).join('');
    lucide.createIcons({ nodes: [list] });

    list.querySelectorAll('.btn-delete-doc').forEach(btn => {
      btn.addEventListener('click', () => knowledge.deleteDocument(btn.dataset.id));
    });
  },

  /* ── Scripts ─────────────────────────────────────────────────── */
  async loadScripts() {
    const list = document.getElementById('scripts-list');
    if (list) {
      list.innerHTML = `<div class="loading-state"><div class="spinner"></div><p>Loading scripts…</p></div>`;
    }
    try {
      state.scripts = (await api.getScripts()) || [];
      ui._renderScripts();
      ui._populateScriptSelectors();
    } catch (e) {
      if (list) list.innerHTML = `<div class="loading-state" style="color:var(--red)">${escapeHtml(e.message)}</div>`;
      toast.error(`Load scripts: ${e.message}`);
    }
  },

  _renderScripts() {
    const list = document.getElementById('scripts-list');
    if (!list) return;
    if (!state.scripts.length) {
      list.innerHTML = `<div class="loading-state"><p style="color:var(--text-muted)">No scripts created yet. Click "Add Script →" above to create your first call script.</p></div>`;
      return;
    }
    list.innerHTML = state.scripts.map(s => `
      <div class="card" style="margin-bottom:1rem; border-left:3px solid var(--color-lime,#c5f82a);" data-script-id="${s.id}">
        <div class="card-header" style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
          <div>
            <h2 style="font-size:1rem; margin:0;"><i data-lucide="file-text"></i> ${escapeHtml(s.title)}</h2>
            <span style="font-size:0.7rem; color:var(--text-muted); font-family:monospace;">ID #${s.id}</span>
          </div>
          <div style="display:flex; gap:0.5rem;">
            <button class="btn btn-outline btn-sm btn-view-script" data-id="${s.id}" title="Preview / collapse script">
              <i data-lucide="eye"></i> Preview
            </button>
            <button class="btn-delete btn-delete-script" data-id="${s.id}" title="Delete script">
              <i data-lucide="trash-2"></i>
            </button>
          </div>
        </div>
        <div class="script-preview" id="script-preview-${s.id}" style="display:block; padding:1rem 1.25rem; background:rgba(255,255,255,0.03); border-radius:6px; margin:0 1.25rem 1.25rem; font-family:monospace; font-size:0.8rem; line-height:1.5; white-space:pre-wrap; color:var(--text-secondary); max-height:220px; overflow-y:auto; border:1px solid var(--border);">${escapeHtml(s.content)}</div>
      </div>
    `).join('');
    lucide.createIcons({ nodes: [list] });

    list.querySelectorAll('.btn-view-script').forEach(btn => {
      btn.addEventListener('click', () => {
        const preview = document.getElementById(`script-preview-${btn.dataset.id}`);
        if (preview) {
          preview.style.display = preview.style.display === 'none' ? 'block' : 'none';
        }
      });
    });

    list.querySelectorAll('.btn-delete-script').forEach(btn => {
      btn.addEventListener('click', async () => {
        if (!confirm('Are you sure you want to delete this script?')) return;
        try {
          await api.deleteScript(btn.dataset.id);
          toast.success('Script deleted.');
          ui.loadScripts();
        } catch (e) {
          toast.error(`Delete failed: ${e.message}`);
        }
      });
    });
  },

  _populateScriptSelectors() {
    const sel = document.getElementById('sim-script-select');
    if (!sel) return;
    const currentVal = sel.value;
    sel.innerHTML = `<option value="">— No script (free-form conversation) —</option>` +
      (state.scripts || []).map(s => `<option value="${s.id}">${escapeHtml(s.title)}</option>`).join('');
    if (currentVal && state.scripts.some(s => s.id == currentVal)) {
      sel.value = currentVal;
    }
  },

  /* ── History ────────────────────────────────────────────────── */
  async loadHistory() {
    const tbody = document.getElementById('history-tbody');
    tbody.innerHTML = `<tr><td colspan="6" class="empty-row"><div class="spinner"></div></td></tr>`;
    try {
      const [calls, contacts] = await Promise.all([api.getCalls(), api.getContacts()]);
      state.calls    = calls    || [];
      state.contacts = contacts || [];
      history_.render(state.calls);
    } catch (e) {
      tbody.innerHTML = `<tr><td colspan="6" class="empty-row" style="color:var(--red)">${escapeHtml(e.message)}</td></tr>`;
      toast.error(`Load history: ${e.message}`);
    }
  },

  /* ── Settings ───────────────────────────────────────────────── */
  loadSettings() {
    const saved = localStorage.getItem(LS_KEY) || DEFAULT_BACKEND_URL;
    const inp = document.getElementById('backend-url-input');
    if (inp) inp.value = saved;
    if (saved) {
      checkBackendHealth(saved);
    } else {
      updateStatusUI(false, 'Not connected');
    }
    if (typeof twilioManager !== 'undefined' && twilioManager.loadConfig) {
      twilioManager.loadConfig();
    }
  },
};

/* ─── Simulator Module ──────────────────────────────────────────── */
const simulator = {

  updateVoiceBadge() {
    const badge = document.getElementById('sim-voice-badge');
    const text  = document.getElementById('sim-voice-text');
    if (!badge || !text) return;
    if (state.voiceStatus && state.voiceStatus.has_voice_clone) {
      badge.className = 'voice-badge active';
      text.textContent = `Cloned Voice: ${state.voiceStatus.filename} (${state.voiceStatus.size_kb} KB)`;
    } else {
      badge.className = 'voice-badge inactive';
      text.textContent = 'No Voice Clone (Upload in Studio)';
    }
  },

  setPipelineStatus(stage, customText = null) {
    const el = document.getElementById('stage-indicator');
    const textEl = document.getElementById('stage-text');
    const iconEl = document.getElementById('stage-icon');
    if (!el || !textEl) return;

    el.className = 'pipeline-stage ' + stage;

    const stages = {
      ready:        { icon: 'check-circle-2', text: 'System Ready' },
      listening:    { icon: 'mic',            text: 'Listening... (Speak now)' },
      thinking:     { icon: 'cpu',            text: 'Alex Thinking (Groq LLM)...' },
      synthesizing: { icon: 'loader-2',       text: 'Generating Cloned Voice (Chatterbox)...' },
      speaking:     { icon: 'volume-2',       text: 'Alex Speaking (Cloned Voice)...' },
      error:        { icon: 'alert-circle',   text: customText || 'Voice synthesis warning' },
    };

    const s = stages[stage] || stages.ready;
    textEl.textContent = customText || s.text;
    if (iconEl) {
      iconEl.innerHTML = `<i data-lucide="${s.icon}"></i>`;
      lucide.createIcons({ nodes: [iconEl] });
    }
    simulator.updateVoiceBadge();
  },

  getActiveContactId() {
    const mode = state.callMode;
    if (mode === 'inbound') {
      // Return the matched contact or null
      return state.currentContact?.id || null;
    } else if (mode === 'marketing') {
      return parseInt(document.getElementById('contact-select-mkt')?.value, 10) || null;
    } else {
      return parseInt(document.getElementById('contact-select')?.value, 10) || null;
    }
  },

  async startCall() {
    const mode = state.callMode;
    let contact = null;
    let contactId = simulator.getActiveContactId();

    if (mode === 'inbound') {
      // Allow unknown callers — start with no contact context
      contact = state.currentContact || { id: null, name: 'Unknown Caller' };
    } else {
      if (!contactId) {
        toast.info('Please select a contact first.');
        return;
      }
      contact = state.contacts.find(c => c.id === contactId) || { id: contactId, name: `Contact #${contactId}` };
    }

    state.currentContact = contact;
    state.transcript = [];
    state.callActive = true;
    state.isSpeaking = false;
    state.timerSeconds = 0;

    document.getElementById('phone-contact-name').textContent = contact.name || 'Unknown Caller';
    document.getElementById('phone-mode-tag').textContent = {
      outbound:  'Outbound Call',
      inbound:   'Inbound Call',
      marketing: 'Marketing Call',
    }[mode] || mode;

    document.getElementById('btn-start-call').disabled = true;
    document.getElementById('btn-end-call').disabled   = false;
    document.getElementById('call-timer-wrap').style.display = 'block';
    document.getElementById('conversation-log').innerHTML = '';
    document.getElementById('stt-preview').innerHTML = '<span class="stt-placeholder">Listening for speech…</span>';
    document.getElementById('analysis-results').style.display = 'none';
    document.getElementById('analysis-placeholder').style.display = 'flex';

    // Alex will speak initial greeting first; microphone activates after Alex finishes
    simulator.setMicState('idle');
    document.getElementById('mic-status').textContent = 'Connecting…';

    state.timerInterval = setInterval(() => {
      state.timerSeconds++;
      const m = String(Math.floor(state.timerSeconds / 60)).padStart(2, '0');
      const s = String(state.timerSeconds % 60).padStart(2, '0');
      document.getElementById('call-timer').textContent = `${m}:${s}`;
    }, 1000);

    // Initial greeting based on mode + selected voice engine + language
    let initialGreeting = null;
    const _greetSimSel = document.getElementById('sim-tts-engine');
    let _greetEngine = _greetSimSel?.value || 'f5tts';
    const simLang = state.selectedLanguage || document.getElementById('sim-language')?.value || 'en-US';

    // Auto-adjust voice engine if Kannada or Hindi is selected
    if (simLang === 'kn-IN') {
      _greetEngine = _greetEngine.includes('kannada') ? _greetEngine : 'kannada_female';
      if (_greetSimSel) _greetSimSel.value = _greetEngine;
    } else if (simLang === 'hi-IN') {
      _greetEngine = _greetEngine.includes('hindi') ? _greetEngine : 'hindi_female';
      if (_greetSimSel) _greetSimSel.value = _greetEngine;
    }

    // For Polly/Joanna/Matthew: use their actual pre-rendered greeting phrase
    const _isJoanna = _greetEngine === 'polly_joanna' || _greetEngine === 'joanna';
    const _isMatthew = _greetEngine === 'polly_matthew' || _greetEngine === 'matthew';
    const _isNativePolly = _greetEngine === 'polly';

    if (simLang === 'kn-IN') {
      const cName = state.currentContact?.name || contact?.name || 'ಸ್ನೇಹಿತರೆ';
      if (mode === 'inbound') {
        initialGreeting = state.currentContact?.id
          ? `ನಮಸ್ಕಾರ ${cName}! ವೋಕಲಿಕ್ಸ್‌ಗೆ ಸ್ವಾಗತ, ನಾನು ಅಲೆಕ್ಸ್. ನಾನು ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಲಿ?`
          : "ನಮಸ್ಕಾರ, ವೋಕಲಿಕ್ಸ್‌ಗೆ ಸ್ವಾಗತ! ನನ್ನ ಹೆಸರು ಅಲೆಕ್ಸ್. ನಾನು ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಬಲ್ಲೆನು?";
      } else if (mode === 'marketing') {
        initialGreeting = `ನಮಸ್ಕಾರ ${cName}! ವೋಕಲಿಕ್ಸ್‌ನಿಂದ ಅಲೆಕ್ಸ್ ಮಾತನಾಡುತ್ತಿದ್ದೇನೆ. ಒಂದು ನಿಮಿಷ ಸಮಯವಿದೆಯೇ?`;
      } else {
        initialGreeting = `ನಮಸ್ಕಾರ ${cName}! ವೋಕಲಿಕ್ಸ್‌ನಿಂದ ಅಲೆಕ್ಸ್ ಮಾತನಾಡುತ್ತಿದ್ದೇನೆ. ಹೇಗಿದ್ದೀರಾ?`;
      }
    } else if (simLang === 'hi-IN') {
      const cName = state.currentContact?.name || contact?.name || 'जी';
      if (mode === 'inbound') {
        initialGreeting = state.currentContact?.id
          ? `नमस्ते ${cName}! वोकलिक्स में आपका स्वागत है, मैं एलेक्स बोल रहा हूँ। मैं आपकी क्या मदद कर सकता हूँ?`
          : "नमस्ते, वोकलिक्स में आपका स्वागत है! मेरा नाम एलेक्स है। मैं आपकी क्या मदद कर सकता हूँ?";
      } else if (mode === 'marketing') {
        initialGreeting = `नमस्ते ${cName}! वोकलिक्स से एलेक्स बोल रहा हूँ। क्या आपके पास एक मिनट का समय है?`;
      } else {
        initialGreeting = `नमस्ते ${cName}! वोकलिक्स से एलेक्स बोल रहा हूँ। आप कैसे हैं?`;
      }
    } else if (mode === 'inbound') {
      if (_isJoanna) {
        initialGreeting = state.currentContact?.id
          ? `Hello ${state.currentContact.name}! Thanks for calling Vocalyx, this is Joanna. How can I help you today?`
          : "Hello, thank you for calling Vocalyx! My name is Joanna. How may I assist you today?";
      } else if (_isMatthew || _isNativePolly) {
        initialGreeting = state.currentContact?.id
          ? `Hello ${state.currentContact.name}! Thanks for calling Vocalyx, this is Matthew. How can I help you today?`
          : "Hello there, thank you for calling Vocalyx. This is Matthew speaking. How can I help you today?";
      } else {
        initialGreeting = state.currentContact?.id
          ? `Hello ${state.currentContact.name}! Thanks for calling Vocalyx, this is Alex. How can I help you today?`
          : "Hello, thank you for calling Vocalyx! My name is Alex. Who do I have the pleasure of speaking with today?";
      }
    } else if (mode === 'marketing') {
      if (_isJoanna) {
        initialGreeting = `Hi ${contact.name}! This is Joanna calling from Vocalyx. I'm reaching out with an exciting opportunity for you. Do you have a quick minute?`;
      } else if (_isMatthew || _isNativePolly) {
        initialGreeting = `Hi ${contact.name}! This is Matthew calling from Vocalyx. I'm reaching out with an exciting opportunity for you. Do you have a quick minute?`;
      } else {
        initialGreeting = `Hi ${contact.name}! This is Alex calling from Vocalyx. I'm reaching out with an exciting opportunity for you. Do you have a quick minute?`;
      }
    } else if (mode === 'outbound') {
      if (_isJoanna) {
        initialGreeting = `Hello ${contact.name}! This is Joanna calling from Vocalyx. How are you doing today?`;
      } else if (_isMatthew || _isNativePolly) {
        initialGreeting = `Hello ${contact.name}! This is Matthew calling from Vocalyx. How are you doing today?`;
      } else {
        initialGreeting = `Hello ${contact.name}! This is Alex calling from Vocalyx. How are you doing today?`;
      }
    }

    toast.success(`Call started — ${mode} mode`);

    if (initialGreeting) {
      state.transcript.push({ role: 'agent', text: initialGreeting });

      let audioUrl = null;
      if (state.backendOk) {
        const simSel = document.getElementById('sim-tts-engine');
        const ttsEngine = simSel?.value || 'f5tts';
        const activeVoiceId = simSel?.selectedOptions?.[0]?.dataset?.voiceId || null;

        // Instant 0.0s start only if greeting already pre-warmed for this exact voice (English only)
        const prewarmMatchesVoice = !activeVoiceId || !voicePrewarmManager.activeVoiceId || String(activeVoiceId) === String(voicePrewarmManager.activeVoiceId);
        if (voicePrewarmManager.isReady && voicePrewarmManager.greetingUrl && simLang === 'en-US' && prewarmMatchesVoice) {
          audioUrl = voicePrewarmManager.greetingUrl;
        } else {
          simulator.setPipelineStatus('synthesizing', `Generating Alex greeting (${ttsEngine.toUpperCase()})...`);
          try {
            const res = await Promise.race([
              api.post('/api/tts', {
                text: initialGreeting,
                engine: ttsEngine,
                voice_id: activeVoiceId ? parseInt(activeVoiceId) : null,
              }),
              new Promise((_, reject) => setTimeout(() => reject(new Error('timeout')), 20000)),
            ]);
            if (res && res.audio_url) {
              audioUrl = res.audio_url;
            }
          } catch (err) {
            console.warn('[TTS] Greeting synthesis issue:', err);
            simulator.setPipelineStatus('error', 'Voice generation slow or failed on server');
          }
        }
      }

      await simulator.speak(initialGreeting, audioUrl);
    }
  },

  async endCall() {
    state.callActive = false;
    state.isSpeaking = false;
    state.currentSpeakingText = null;
    state.chatRequestId++;
    clearInterval(state.timerInterval);

    if (state.silenceTimer) {
      clearTimeout(state.silenceTimer);
      state.silenceTimer = null;
    }
    state.activeSpeech = '';

    if (window.speechSynthesis) {
      try { window.speechSynthesis.cancel(); } catch {}
    }
    if (state.currentAudio) {
      try { state.currentAudio.pause(); state.currentAudio = null; } catch {}
    }

    if (state.recognition) {
      try {
        state.recognition.onresult = null;
        state.recognition.onend = null;
        state.recognition.abort();
      } catch {}
      state.recognition = null;
    }

    simulator.setMicState('idle');
    simulator.setPipelineStatus('ready', 'Call Ended');
    document.getElementById('btn-start-call').disabled = false;
    document.getElementById('btn-end-call').disabled   = true;

    if (!state.transcript.length) {
      toast.info('No conversation to analyze.');
      return;
    }

    simulator.setMicState('thinking');
    document.getElementById('mic-status').textContent = 'Analyzing…';
    simulator.setPipelineStatus('thinking', 'Analyzing call conversation...');

    const transcriptStr = state.transcript
      .map(m => `${m.role === 'user' ? 'User' : 'Agent'}: ${m.text}`)
      .join('\n');

    try {
      const contactId = simulator.getActiveContactId() || 0;
      const result = await api.analyzeCall({
        contact_id: contactId,
        transcript: transcriptStr,
      });
      simulator.showAnalysis(result);
      toast.success('Call analysis complete!');
      ui.loadDashboard();
      ui.loadHistory();
    } catch (e) {
      console.warn('[Simulator Analysis Warning]:', e);
      toast.error(`Analysis note: ${e.message}`);
      simulator.showAnalysis({
        lead_score: 50,
        sentiment: 'Neutral',
        outcome: 'Needs Follow-up',
        lead_score_reasoning: `Call recorded (${state.transcript.length} turns). Server note: ${e.message}`,
        summary: 'Call completed. Full audio and transcript registered.',
      });
    } finally {
      simulator.setMicState('idle');
      simulator.setPipelineStatus('ready');
    }
  },

  showAnalysis(result) {
    document.getElementById('analysis-placeholder').style.display = 'none';
    document.getElementById('analysis-results').style.display = 'block';

    const score = result.lead_score || 0;
    const circumference = 314;
    const offset = circumference - (score / 100) * circumference;
    const fillEl = document.getElementById('score-fill-circle');
    if (fillEl) {
      fillEl.style.strokeDashoffset = offset;
      fillEl.style.stroke = score >= 70 ? 'var(--accent-dark)' : score >= 40 ? 'var(--yellow)' : 'var(--red)';
    }
    const scoreEl = document.getElementById('score-number');
    if (scoreEl) scoreEl.textContent = score;

    const sentEl = document.getElementById('analysis-sentiment');
    if (sentEl) sentEl.innerHTML = sentimentBadge(result.sentiment);

    const outEl = document.getElementById('analysis-outcome');
    if (outEl) outEl.innerHTML = outcomeBadge(result.outcome);

    const reasEl = document.getElementById('analysis-reasoning');
    if (reasEl) reasEl.textContent = result.lead_score_reasoning || '—';

    const sumEl = document.getElementById('analysis-summary');
    if (sumEl) sumEl.textContent = result.summary || '—';

    renderAlertStatusRows(result, 'sim');
  },

  async handleUserMessage(text) {
    if (!text || !state.callActive) return;

    if (state.silenceTimer) {
      clearTimeout(state.silenceTimer);
      state.silenceTimer = null;
    }
    state.activeSpeech = '';

    // Stop recognition while waiting for AI response
    simulator.stopRecognition();
    simulator.setMicState('thinking');
    simulator.setPipelineStatus('thinking', 'Alex is thinking (Groq LLM)...');

    const previewEl = document.getElementById('stt-preview');
    if (previewEl) {
      previewEl.innerHTML = '<span class="stt-placeholder">Alex is preparing response…</span>';
    }
    simulator.addBubble('user', text);
    state.transcript.push({ role: 'user', text });

    const reqId = ++state.chatRequestId;

    // For inbound unknown callers — try to match from name in transcript
    if (state.callMode === 'inbound' && !state.currentContact?.id) {
      const matched = state.contacts.find(c =>
        c.name && text.toLowerCase().includes(c.name.toLowerCase().split(' ')[0])
      );
      if (matched) {
        state.currentContact = matched;
        document.getElementById('phone-contact-name').textContent = matched.name;
      }
    }

    try {
      const simSel = document.getElementById('sim-tts-engine');
      const ttsEngine = simSel?.value || 'f5tts';
      const activeVoiceId = simSel?.selectedOptions?.[0]?.dataset?.voiceId || null;
      const simScriptSel = document.getElementById('sim-script-select');
      const activeScriptId = simScriptSel?.value ? parseInt(simScriptSel.value) : null;
      const simLang = state.selectedLanguage || document.getElementById('sim-language')?.value || 'en-US';

      const res = await api.chat({
        message: text,
        contact_id: state.currentContact?.id || 0,
        tts_engine: ttsEngine,
        voice_id: activeVoiceId ? parseInt(activeVoiceId) : null,
        conversation_history: state.transcript,
        script_id: activeScriptId,
        language: simLang,
      });

      if (reqId !== state.chatRequestId) return;

      const agentText = res.response || res.text || res.message || '';
      if (agentText) {
        state.transcript.push({ role: 'agent', text: agentText });

        if (res.audio_url) {
          await simulator.speak(agentText, res.audio_url);
        } else {
          simulator.addBubble('agent', agentText);
          if (res.tts_error) {
            simulator.setPipelineStatus('error', `Voice warning: ${res.tts_error}`);
            toast.error(`Voice synthesis: ${res.tts_error}`);
          }
          if (state.callActive && !state.isSpeaking) {
            simulator.setMicState('listening');
            simulator.setPipelineStatus('listening', 'Listening for your reply... (Speak now)');
            simulator.startRecognition();
          }
        }
      } else {
        if (state.callActive && !state.isSpeaking) {
          simulator.setMicState('listening');
          simulator.setPipelineStatus('listening', 'Listening for your reply... (Speak now)');
          simulator.startRecognition();
        }
      }
    } catch (e) {
      if (reqId !== state.chatRequestId) return;
      toast.error(`Chat error: ${e.message}`);
      simulator.setPipelineStatus('error', `Chat error: ${e.message}`);
      if (state.callActive && !state.isSpeaking) {
        simulator.setMicState('listening');
        simulator.startRecognition();
      }
    }
  },

  stopRecognition() {
    if (state.recognition) {
      try {
        state.recognition.onstart = null;
        state.recognition.onend = null;
        state.recognition.onresult = null;
        state.recognition.onerror = null;
        state.recognition.abort();
      } catch {}
      state.recognition = null;
    }
  },

  startRecognition() {
    if (!state.callActive || state.isSpeaking || state.currentAudio) return;

    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) {
      toast.error('Web Speech API not supported. You can type below instead.');
      return;
    }

    if (state.recognition) {
      return;
    }

    if (state.silenceTimer) {
      clearTimeout(state.silenceTimer);
      state.silenceTimer = null;
    }

    const rec = new SR();
    state.recognition = rec;
    rec.continuous     = true;
    rec.interimResults = true;
    rec.lang           = state.selectedLanguage || document.getElementById('sim-language')?.value || 'en-US';

    rec.onstart = () => {
      if (!state.callActive || state.isSpeaking) {
        try { rec.stop(); } catch {}
        return;
      }
      simulator.setMicState('listening');
      simulator.setPipelineStatus('listening', 'Listening... (Speak now)');
    };

    rec.onresult = (event) => {
      if (!state.callActive) return;

      // Acoustic echo rejection: ignore all microphone input while AI audio is playing
      if (state.isSpeaking || state.currentAudio) {
        return;
      }

      let interim = '';
      let final = '';

      for (let i = event.resultIndex; i < event.results.length; ++i) {
        const item = event.results[i];
        const text = item[0]?.transcript || '';
        if (item.isFinal) {
          final += text + ' ';
        } else {
          interim += text;
        }
      }

      if (final) {
        state.activeSpeech = (state.activeSpeech + ' ' + final).trim();
      }

      const liveText = (state.activeSpeech + ' ' + interim).trim();
      const heardWords = extractWords(liveText);
      if (heardWords.length === 0) return;

      // Echo cancellation: reject recognized speech if it echoes Alex's recently spoken phrase
      if (state.lastAgentSpokenText && liveText.length > 2) {
        const cleanLive = liveText.toLowerCase().replace(/[^\w\s]/g, '').trim();
        const cleanAgent = (state.lastAgentSpokenText || '').toLowerCase().replace(/[^\w\s]/g, '').trim();
        if (cleanAgent && (cleanAgent.includes(cleanLive) || (cleanLive.length < 25 && cleanAgent.startsWith(cleanLive)))) {
          console.log('[STT Echo Filter] Ignored agent speaker loopback:', liveText);
          return;
        }
      }

      // Real-time visual feedback with instant Send button
      const previewEl = document.getElementById('stt-preview');
      if (previewEl) {
        previewEl.innerHTML = `
          <div style="display:flex; align-items:center; justify-content:space-between; width:100%; gap:8px;">
            <span style="color:var(--text); font-style:normal; font-weight:600; flex:1;">🗣️ "${escapeHtml(liveText)}"</span>
            <button class="btn btn-lime btn-sm" id="btn-quick-send-stt" style="padding:2px 8px; font-size:0.75rem; white-space:nowrap; cursor:pointer;">
              Send ↵
            </button>
          </div>
        `;
        document.getElementById('btn-quick-send-stt')?.addEventListener('click', (e) => {
          e.stopPropagation();
          if (state.silenceTimer) clearTimeout(state.silenceTimer);
          state.silenceTimer = null;
          simulator.handleUserMessage(liveText);
        });
      }
      simulator.setMicState('listening');
      simulator.setPipelineStatus('listening', 'Hearing your voice... (pause 1.4s or click Send ↵)');

      if (state.silenceTimer) {
        clearTimeout(state.silenceTimer);
      }

      // 1.4s silence threshold: spontaneous, responsive conversation without interruption
      state.silenceTimer = setTimeout(() => {
        const toSend = (state.activeSpeech + ' ' + interim).trim();
        const validWords = extractWords(toSend);
        if (validWords.length > 0 && state.callActive && !state.isSpeaking) {
          state.activeSpeech = '';
          if (state.silenceTimer) {
            clearTimeout(state.silenceTimer);
            state.silenceTimer = null;
          }
          simulator.handleUserMessage(toSend);
        }
      }, 1400);
    };

    rec.onerror = (e) => {
      if (e.error === 'no-speech' || e.error === 'aborted') {
        return;
      }
      console.warn('[Speech] Error:', e.error);
    };

    rec.onend = () => {
      state.recognition = null;
      if (state.callActive && !state.isSpeaking && !state.currentAudio) {
        setTimeout(() => {
          if (state.callActive && !state.isSpeaking && !state.currentAudio) {
            simulator.startRecognition();
          }
        }, 150);
      }
    };

    try {
      rec.start();
    } catch (err) {
      console.warn('[Speech] Start failed:', err);
    }
  },

  async fetchAudioBlob(url) {
    const res = await fetch(url, {
      cache: 'no-store',
      headers: { 'ngrok-skip-browser-warning': 'true' },
    });
    if (!res.ok) throw new Error(`Audio fetch HTTP ${res.status}`);
    const ct = (res.headers.get('content-type') || '').toLowerCase();
    if (ct.includes('text/html')) {
      throw new Error('Server returned HTML instead of WAV audio (check ngrok URL)');
    }
    const blob = await res.blob();
    if (!blob || blob.size <= 44) {
      throw new Error('Synthesized audio file is empty (0 bytes)');
    }
    return URL.createObjectURL(blob);
  },

  playAudio(url, onStart = null) {
    return new Promise(resolve => {
      const audio = new Audio(url);
      audio.volume = 1.0;
      state.currentAudio = audio;
      let finished = false;
      const finish = () => {
        if (!finished) {
          finished = true;
          if (state.currentAudio === audio) state.currentAudio = null;
          resolve();
        }
      };

      let triggered = false;
      const trigger = () => {
        if (!triggered && onStart) {
          triggered = true;
          onStart();
        }
      };

      audio.onplay = () => trigger();
      audio.onplaying = () => trigger();
      audio.onpause = () => finish();
      audio.onended = () => finish();
      audio.onerror = () => finish();
      audio.play().then(() => {
        trigger();
      }).catch(() => {
        finish();
      });
    });
  },

  async speak(text, audioUrl = null) {
    if (!state.callActive || !text) return;

    state.isSpeaking = true;
    state.currentSpeakingText = text;
    state.lastAgentSpokenText = text;

    // Turn OFF microphone completely while AI speaks to eliminate acoustic feedback
    simulator.stopRecognition();
    state.activeSpeech = '';
    simulator.setMicState('playing');
    simulator.setPipelineStatus('speaking', 'Alex is Speaking...');

    let bubbleShown = false;
    const revealBubble = () => {
      if (!bubbleShown) {
        bubbleShown = true;
        simulator.addBubble('agent', text);
      }
    };

    if (audioUrl) {
      try {
        const fullUrl = audioUrl.startsWith('http') ? audioUrl : (api.base.replace(/\/$/, '') + audioUrl);
        const blobUrl = await simulator.fetchAudioBlob(fullUrl);
        await simulator.playAudio(blobUrl, () => {
          revealBubble();
        });
        URL.revokeObjectURL(blobUrl);
      } catch (err) {
        console.warn('[Audio] Cloned voice playback failed:', err);
        simulator.setPipelineStatus('error', 'Audio playback issue');
        revealBubble();
      }
    } else {
      revealBubble();
    }

    // Safety acoustic decay buffer: wait 250ms for room echo / speaker reverb to dissipate
    await new Promise(r => setTimeout(r, 250));

    state.activeSpeech = '';
    state.isSpeaking = false;
    state.currentSpeakingText = null;

    if (state.callActive) {
      simulator.setMicState('listening');
      simulator.setPipelineStatus('listening', 'Listening for your reply... (Speak now)');
      const previewEl = document.getElementById('stt-preview');
      if (previewEl && !state.activeSpeech) {
        previewEl.innerHTML = '<span class="stt-placeholder">Listening for speech…</span>';
      }
      simulator.startRecognition();
    }
  },

  addBubble(role, text) {
    const log = document.getElementById('conversation-log');
    const placeholder = log.querySelector('.conv-placeholder');
    if (placeholder) placeholder.remove();

    const div = document.createElement('div');
    div.className = `conv-bubble ${role}`;
    div.innerHTML = `
      <div class="conv-bubble-role">${role === 'user' ? '🎤 You' : '👤 Alex'}</div>
      <div class="conv-bubble-text">${escapeHtml(text)}</div>
    `;
    log.appendChild(div);
    log.scrollTop = log.scrollHeight;
  },

  setMicState(s) {
    const container = document.getElementById('mic-container');
    container.classList.remove('listening', 'thinking', 'playing');
    const icon   = document.getElementById('mic-icon');
    const status = document.getElementById('mic-status');

    const iconMap   = { listening: 'mic', thinking: 'cpu', playing: 'volume-2', idle: 'mic-off' };
    const statusMap = { listening: 'Listening… (speak now)', thinking: 'Thinking…', playing: 'Speaking…', idle: 'Idle' };

    if (s !== 'idle') container.classList.add(s);

    icon.innerHTML = `<i data-lucide="${iconMap[s] || 'mic'}"></i>`;
    status.textContent = statusMap[s] || 'Idle';
    lucide.createIcons({ nodes: [icon] });
  },

  async deleteContact(id) {
    if (!confirm('Delete this contact? This cannot be undone.')) return;
    try {
      await api.deleteContact(id);
      toast.success('Contact deleted.');
      ui.loadContacts();
    } catch (e) {
      toast.error(`Delete failed: ${e.message}`);
    }
  },

  // Caller ID auto-match (inbound mode)
  handleCallerIdInput(value) {
    const hint = document.getElementById('caller-match-hint');
    const box  = document.getElementById('caller-match-box');
    if (!value.trim()) {
      state.currentContact = null;
      box.className = 'caller-match-box';
      box.innerHTML = `<i data-lucide="user-question"></i><span>Unknown caller</span>`;
      lucide.createIcons({ nodes: [box] });
      return;
    }
    const matched = state.contacts.find(c =>
      c.phone_number && c.phone_number.replace(/\D/g,'').includes(value.replace(/\D/g,''))
    );
    if (matched) {
      state.currentContact = matched;
      box.className = 'caller-match-box matched';
      box.innerHTML = `<i data-lucide="user-check"></i><span>${escapeHtml(matched.name)}</span>`;
      lucide.createIcons({ nodes: [box] });
      if (hint) hint.textContent = `✓ Matched to ${matched.name}`;
    } else {
      state.currentContact = null;
      box.className = 'caller-match-box';
      box.innerHTML = `<i data-lucide="user-x"></i><span>No match — Unknown caller</span>`;
      lucide.createIcons({ nodes: [box] });
      if (hint) hint.textContent = 'No contact matched — call will start as unknown inbound';
    }
  },
};

/* ─── Knowledge Base Module ─────────────────────────────────────── */
const knowledge = {

  async uploadFiles(files) {
    for (const file of files) {
      const fd    = new FormData();
      fd.append('file', file);
      const wrap  = document.getElementById('upload-progress-wrap');
      const bar   = document.getElementById('upload-progress-bar');
      const label = document.getElementById('upload-progress-label');

      wrap.style.display = 'block';
      bar.style.width    = '30%';
      label.textContent  = `Uploading ${file.name}…`;

      try {
        await api.uploadDocument(fd);
        bar.style.width   = '100%';
        label.textContent = `✓ ${file.name} indexed!`;
        toast.success(`"${file.name}" uploaded successfully!`);
        await ui.loadDocuments();
      } catch (e) {
        bar.style.width      = '100%';
        bar.style.background = 'var(--red)';
        label.textContent    = `✗ ${file.name}: ${e.message}`;
        toast.error(`Upload failed: ${e.message}`);
      } finally {
        setTimeout(() => {
          wrap.style.display   = 'none';
          bar.style.width      = '0';
          bar.style.background = '';
        }, 2500);
      }
    }
  },

  async deleteDocument(id) {
    if (!confirm('Remove this document from the knowledge base?')) return;
    try {
      await api.deleteDocument(id);
      toast.success('Document removed.');
      ui.loadDocuments();
    } catch (e) {
      toast.error(`Delete failed: ${e.message}`);
    }
  },
};

/* ─── Voices Manager Module ─────────────────────────────────────── */
const voicesManager = {
  selectedFile: null,
  computedData: null,
  voices: [],

  setFile(file) {
    this.selectedFile = file;
    const info = document.getElementById('voice-file-info');
    const nameEl = document.getElementById('voice-file-name');
    const sizeEl = document.getElementById('voice-file-size');
    if (info && nameEl) {
      nameEl.textContent = file.name;
      if (sizeEl) sizeEl.textContent = `${(file.size / 1024).toFixed(1)} KB`;
      info.style.display = 'flex';
      lucide.createIcons({ nodes: [info] });
    }
    const nameInp = document.getElementById('new-voice-name');
    if (nameInp && !nameInp.value.trim()) {
      const clean = file.name.replace(/\.[^/.]+$/, '').replace(/[_-]/g, ' ');
      nameInp.value = clean.charAt(0).toUpperCase() + clean.slice(1);
    }
  },

  async loadVoices() {
    const grid = document.getElementById('voices-grid');
    const countEl = document.getElementById('voices-count');
    if (grid && !this.voices.length) {
      grid.innerHTML = `<div class="loading-state"><div class="spinner"></div><p>Loading voices…</p></div>`;
    }

    try {
      const voices = await api.getVoices();
      this.voices = voices || [];
      state.voices = this.voices;
      if (countEl) countEl.textContent = `${this.voices.length} voices`;
      this.renderVoices();
      this.syncSelectDropdowns();
    } catch (e) {
      if (grid) {
        grid.innerHTML = `<div class="empty-state"><i data-lucide="alert-triangle"></i><p>Failed to load voices: ${escapeHtml(e.message)}</p></div>`;
        lucide.createIcons({ nodes: [grid] });
      }
    }
  },

  renderVoices() {
    const grid = document.getElementById('voices-grid');
    if (!grid) return;

    if (!this.voices.length) {
      grid.innerHTML = `<div class="empty-state"><i data-lucide="mic-off"></i><p>No voices found in library.</p></div>`;
      lucide.createIcons({ nodes: [grid] });
      return;
    }

    const engineBadge = (engine) => {
      const eng = (engine || '').toLowerCase();
      if (eng === 'f5tts') return 'badge-lime';
      if (eng === 'luxtts') return 'badge-green';
      if (eng === 'polly') return 'badge-blue';
      return 'badge-grey';
    };

    grid.innerHTML = this.voices.map(v => {
      const previewSrc = v.preview_url ? (v.preview_url.startsWith('http') ? v.preview_url : `${api.base.replace(/\/$/, '')}${v.preview_url}`) : null;
      return `
        <div class="voice-card ${v.is_active ? 'active' : ''}" data-id="${v.id}">
          <div class="voice-card-header">
            <div>
              <div class="voice-card-title">${escapeHtml(v.name)}</div>
              <div class="voice-badges-row">
                <span class="badge ${engineBadge(v.engine)}">${v.engine.toUpperCase()}</span>
                <span class="badge badge-grey">${v.voice_type === 'cloned' ? 'Neural Clone' : 'Carrier Native'}</span>
                ${v.is_active ? '<span class="badge badge-lime"><i data-lucide="check" style="width:12px;height:12px;margin-right:2px;"></i> Active</span>' : ''}
              </div>
            </div>
          </div>

          <div class="voice-preview-box">
            ${previewSrc ? `
              <button class="btn btn-outline btn-sm btn-play-voice-preview" data-src="${escapeHtml(previewSrc)}" style="width:100%; justify-content:center; gap:6px;">
                <i data-lucide="volume-2"></i> Play Voice Preview
              </button>
            ` : `
              <button class="btn btn-outline btn-sm btn-test-sample" data-id="${v.id}" data-engine="${v.engine}" style="width:100%; justify-content:center; gap:6px;">
                <i data-lucide="volume-2"></i> Test Speech Sample
              </button>
            `}
          </div>

          <div class="voice-card-footer">
            ${v.is_active ? `
              <span style="font-size:0.75rem; font-weight:700; color:#15803D; display:flex; align-items:center; gap:5px;">
                <span style="display:inline-block; width:8px; height:8px; border-radius:50%; background:#22C55E;"></span> Currently Active
              </span>
            ` : `
              <button class="btn btn-dark btn-sm btn-activate-voice" data-id="${v.id}">
                <i data-lucide="zap"></i> Set as Active
              </button>
            `}

            ${(v.id > 3 && v.voice_type === 'cloned') ? `
              <button class="btn-delete btn-delete-voice" data-id="${v.id}" title="Delete Voice">
                <i data-lucide="trash-2"></i>
              </button>
            ` : `
              <span title="System Default Voice" style="color:var(--text-muted); font-size:0.7rem; display:flex; align-items:center; gap:2px;">
                <i data-lucide="lock" style="width:12px; height:12px;"></i> Default
              </span>
            `}
          </div>
        </div>
      `;
    }).join('');

    lucide.createIcons({ nodes: [grid] });

    grid.querySelectorAll('.btn-activate-voice').forEach(btn => {
      btn.addEventListener('click', () => this.activate(btn.dataset.id));
    });

    grid.querySelectorAll('.btn-delete-voice').forEach(btn => {
      btn.addEventListener('click', () => this.deleteVoice(btn.dataset.id));
    });

    grid.querySelectorAll('.btn-test-sample').forEach(btn => {
      btn.addEventListener('click', () => this.testSample(btn.dataset.engine, btn, btn.dataset.id));
    });

    grid.querySelectorAll('.btn-play-voice-preview').forEach(btn => {
      btn.addEventListener('click', async () => {
        const src = btn.dataset.src;
        if (!src) return;
        btn.disabled = true;
        btn.innerHTML = `<div class="spinner" style="width:12px;height:12px;border-width:2px;"></div> Playing...`;
        try {
          const fullUrl = src.startsWith('http') ? src : `${api.base.replace(/\/$/, '')}${src}`;
          const blobUrl = await simulator.fetchAudioBlob(fullUrl);
          const audio = new Audio(blobUrl);
          const restore = () => {
            btn.disabled = false;
            btn.innerHTML = `<i data-lucide="volume-2"></i> Play Voice Preview`;
            lucide.createIcons({ nodes: [btn] });
            URL.revokeObjectURL(blobUrl);
          };
          audio.onended = restore;
          audio.onerror = restore;
          await audio.play();
        } catch (err) {
          toast.error(`Audio preview failed: ${err.message}`);
          btn.disabled = false;
          btn.innerHTML = `<i data-lucide="volume-2"></i> Play Voice Preview`;
          lucide.createIcons({ nodes: [btn] });
        }
      });
    });
  },

  async testSample(engine, btn, voiceId = null) {
    if (btn) btn.disabled = true;
    const eng = (engine || '').toLowerCase();
    let sampleText = "Hello! This is a test of my AI voice with Vocalyx.";
    if (eng.includes('kannada') || eng.includes('kn')) {
      sampleText = "ನಮಸ್ಕಾರ! ಇದು ವೋಕಲಿಕ್ಸ್‌ನ ಸ್ಟುಡಿಯೋ ಧ್ವನಿಯ ಮಾದರಿಯಾಗಿದೆ.";
    } else if (eng.includes('hindi') || eng.includes('hi')) {
      sampleText = "नमस्ते! यह वोकलिक्स की स्टूडियो ध्वनि का एक परीक्षण है।";
    }
    toast.info(`Generating ${engine.toUpperCase()} speech preview...`);
    try {
      const res = await api.post('/api/tts', {
        text: sampleText,
        engine: engine,
        voice_id: voiceId ? parseInt(voiceId) : null,
      });
      if (res && res.audio_url) {
        const fullUrl = res.audio_url.startsWith('http') ? res.audio_url : `${api.base.replace(/\/$/, '')}${res.audio_url}`;
        const blobUrl = await simulator.fetchAudioBlob(fullUrl);
        const a = new Audio(blobUrl);
        a.play().catch(e => toast.error(`Playback failed: ${e.message}`));
        toast.success(`${engine.toUpperCase()} sample playing!`);
      }
    } catch (e) {
      toast.error(`Sample generation failed: ${e.message}`);
    } finally {
      if (btn) btn.disabled = false;
    }
  },

  async computeVoice() {
    const nameInp = document.getElementById('new-voice-name');
    const engineSel = document.getElementById('new-voice-engine');
    const testTextInp = document.getElementById('new-voice-test-text');
    const computeBtn = document.getElementById('btn-compute-voice');
    const saveBtn = document.getElementById('btn-save-voice');
    const resultBox = document.getElementById('compute-result-box');
    const player = document.getElementById('computed-voice-player');
    const elapsedEl = document.getElementById('compute-elapsed-text');

    const name = (nameInp ? nameInp.value : '').trim();
    const engine = engineSel ? engineSel.value : 'f5tts';
    const testText = (testTextInp ? testTextInp.value : '').trim();

    if (!name) {
      toast.error('Please enter a voice name.');
      nameInp?.focus();
      return;
    }
    if (!this.selectedFile) {
      toast.error('Please upload a reference audio sample (.wav or .mp3).');
      return;
    }

    if (computeBtn) {
      computeBtn.disabled = true;
      computeBtn.innerHTML = `<div class="spinner" style="width:14px;height:14px;border-width:2px;"></div> Computing on GPU…`;
    }
    if (saveBtn) saveBtn.disabled = true;
    if (resultBox) resultBox.style.display = 'none';

    toast.info(`Computing neural voice conditioning for "${name}" on GPU...`);

    const fd = new FormData();
    fd.append('name', name);
    fd.append('engine', engine);
    fd.append('audio', this.selectedFile);
    if (testText) fd.append('test_text', testText);

    try {
      const res = await api.computeVoice(fd);
      this.computedData = res;

      if (resultBox) resultBox.style.display = 'block';
      if (elapsedEl) elapsedEl.textContent = `⚡ Computed in ${res.computation_time_seconds || '2.1'}s`;

      const previewUrl = res.preview_url ? (res.preview_url.startsWith('http') ? res.preview_url : `${api.base.replace(/\/$/, '')}${res.preview_url}`) : '';
      if (player && previewUrl) {
        if (player.dataset.blobUrl) {
          URL.revokeObjectURL(player.dataset.blobUrl);
          delete player.dataset.blobUrl;
        }
        try {
          // Fetch with ngrok-skip-browser-warning header so <audio> receives WAV bytes, not ngrok HTML warning
          const blobUrl = await simulator.fetchAudioBlob(previewUrl);
          player.dataset.blobUrl = blobUrl;
          player.src = blobUrl;
          player.load();
          player.play().catch(() => {});
        } catch (audioErr) {
          console.warn('[Voice Compute] Blob preview fetch failed:', audioErr);
          toast.error(`Preview audio failed to load: ${audioErr.message}`);
        }
      }

      // CRITICAL: Enable Save button now that computation succeeded
      if (saveBtn) {
        saveBtn.disabled = false;
        saveBtn.classList.add('pulse');
      }

      toast.success('Voice conditioning computed! Preview audio is ready. Click "Save Voice to Library".');
    } catch (e) {
      toast.error(`Computation failed: ${e.message}`);
      if (saveBtn) saveBtn.disabled = true;
    } finally {
      if (computeBtn) {
        computeBtn.disabled = false;
        computeBtn.innerHTML = `<i data-lucide="cpu"></i> Compute Voice on GPU →`;
        lucide.createIcons({ nodes: [computeBtn] });
      }
    }
  },

  async saveVoice() {
    if (!this.computedData) {
      toast.error('Please compute the voice conditionals on GPU first.');
      return;
    }

    const saveBtn = document.getElementById('btn-save-voice');
    const chkActivate = document.getElementById('chk-activate-now');
    const activateNow = chkActivate ? chkActivate.checked : true;

    if (saveBtn) {
      saveBtn.disabled = true;
      saveBtn.innerHTML = `<div class="spinner" style="width:14px;height:14px;border-width:2px;"></div> Saving…`;
    }

    try {
      const payload = {
        name: this.computedData.name,
        engine: this.computedData.engine,
        audio_path: this.computedData.audio_path,
        preview_url: this.computedData.preview_url,
        activate_now: activateNow,
      };

      const res = await api.saveVoice(payload);
      toast.success(`Voice "${res.name}" saved to library!`);

      if (activateNow && res.id) {
        this._preferredVoiceId = String(res.id);
      }

      this.resetAddForm();
      this.toggleAddCard(false);

      await this.loadVoices();
      if (typeof voicePrewarmManager !== 'undefined') {
        voicePrewarmManager.checkStatus();
      }

      if (activateNow) {
        toast.info(`Active voice set to "${res.name}" (${res.engine.toUpperCase()})`);
      }
    } catch (e) {
      toast.error(`Failed to save voice: ${e.message}`);
      if (saveBtn) saveBtn.disabled = false;
    }
  },

  async activate(voiceId) {
    this._preferredVoiceId = String(voiceId);
    toast.info('Activating voice on server and pre-warming GPU...');
    try {
      const res = await api.activateVoice(voiceId);
      if (res && res.success) {
        this._preferredVoiceId = String(res.active_voice?.id || voiceId);
        toast.success(`Voice "${res.active_voice.name}" is now active!`);
        await this.loadVoices();
        if (typeof voicePrewarmManager !== 'undefined') {
          voicePrewarmManager.checkStatus();
        }
      }
    } catch (e) {
      toast.error(`Activation failed: ${e.message}`);
    }
  },

  async deleteVoice(voiceId) {
    if (!confirm('Are you sure you want to remove this custom voice from your library?')) return;
    try {
      await api.deleteVoice(voiceId);
      toast.success('Voice deleted.');
      await this.loadVoices();
    } catch (e) {
      toast.error(`Delete failed: ${e.message}`);
    }
  },

  resetAddForm() {
    this.selectedFile = null;
    this.computedData = null;
    const nameInp = document.getElementById('new-voice-name');
    const testTextInp = document.getElementById('new-voice-test-text');
    const fileInfo = document.getElementById('voice-file-info');
    const fileInp = document.getElementById('voice-file-input');
    const resultBox = document.getElementById('compute-result-box');
    const saveBtn = document.getElementById('btn-save-voice');

    if (nameInp) nameInp.value = '';
    if (testTextInp) testTextInp.value = '';
    if (fileInfo) fileInfo.style.display = 'none';
    if (fileInp) fileInp.value = '';
    if (resultBox) resultBox.style.display = 'none';
    if (saveBtn) saveBtn.disabled = true;
  },

  toggleAddCard(show = null) {
    const card = document.getElementById('card-add-voice');
    if (!card) return;
    const isVisible = card.style.display !== 'none';
    const target = show !== null ? show : !isVisible;
    card.style.display = target ? 'block' : 'none';
    if (target) {
      lucide.createIcons({ nodes: [card] });
      card.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  },

  syncSelectDropdowns() {
    const phoneSel = document.getElementById('phone-tts-engine');
    const simSel = document.getElementById('sim-tts-engine');

    if (!this.voices || !this.voices.length) return;

    // ── Fallback: ensure standard engines exist in this.voices if API didn't return them ──
    // We only ADD engines not already present (by engine key). This prevents duplicates.
    const standardFallbacks = [
      { engine: 'f5tts',          name: 'Alex (Default F5-TTS Flow-Matching)', voice_type: 'cloned' },
      { engine: 'polly_joanna',   name: 'Joanna (Natural US Female)',           voice_type: 'native' },
      { engine: 'polly_matthew',  name: 'Matthew (Natural US Male)',            voice_type: 'native' },
      { engine: 'kannada_female', name: 'Sapna (Kannada Female Studio)',        voice_type: 'native' },
      { engine: 'kannada_male',   name: 'Gagan (Kannada Male Studio)',          voice_type: 'native' },
      { engine: 'hindi_female',   name: 'Swara (Hindi Female Studio)',          voice_type: 'native' },
      { engine: 'hindi_male',     name: 'Madhur (Hindi Male Studio)',           voice_type: 'native' },
      { engine: 'luxtts',         name: 'Alex (LuxTTS Ultra-Fast 150x)',        voice_type: 'cloned' },
    ];

    const currentEngines = new Set(this.voices.map(v => v.engine));
    standardFallbacks.forEach((se, idx) => {
      if (!currentEngines.has(se.engine)) {
        this.voices.push({ id: 100 + idx, name: se.name, engine: se.engine, voice_type: se.voice_type, is_active: false, preview_url: null });
      }
    });

    const activeVoice = this.voices.find(v => v.is_active) || this.voices[0];

    const buildVoiceLabel = (v) => {
      const eng = (v.engine || '').toLowerCase();
      if (eng === 'kannada_female') return `Sapna (Kannada Female Studio) — Kannada (Studio Neural)`;
      if (eng === 'kannada_male')   return `Gagan (Kannada Male Studio) — Kannada (Studio Neural)`;
      if (eng === 'hindi_female')   return `Swara (Hindi Female Studio) — Hindi (Studio Neural)`;
      if (eng === 'hindi_male')     return `Madhur (Hindi Male Studio) — Hindi (Studio Neural)`;
      if (eng === 'f5tts')          return `${v.name} — Cloned Voice (English Only)`;
      if (eng === 'luxtts')         return `${v.name} — Cloned Voice (English Only)`;
      if (eng === 'polly_joanna')   return `Joanna (Natural US Female) — English (Studio)`;
      if (eng === 'polly_matthew')  return `Matthew (Natural US Male) — English (Studio)`;
      // User-uploaded cloned voices
      if (v.voice_type === 'cloned') return `${v.name} — Cloned Voice (English Only)`;
      return `${v.name} — English (Studio)`;
    };

    const curPhoneVoiceId = phoneSel?.selectedOptions?.[0]?.dataset?.voiceId || null;
    const curSimVoiceId = simSel?.selectedOptions?.[0]?.dataset?.voiceId || null;
    const curPhoneVal = phoneSel?.value;
    const curSimVal = simSel?.value;

    // Build options once — mark server-active voice selected cleanly
    const optionsHtml = this.voices.map(v => {
      const lbl = buildVoiceLabel(v);
      return `<option value="${v.engine}" data-voice-id="${v.id}" data-voice-type="${v.voice_type}" data-orig-text="${escapeHtml(lbl)}" ${v.is_active ? 'selected' : ''}>${escapeHtml(lbl)}</option>`;
    }).join('');

    const restoreVoiceSelection = (sel, prevVoiceId, prevEngineVal) => {
      if (!sel) return;
      const targetVoiceId = this._preferredVoiceId || (activeVoice ? String(activeVoice.id) : null) || prevVoiceId;
      const opts = Array.from(sel.options);
      let idx = targetVoiceId ? opts.findIndex(o => o.dataset.voiceId === String(targetVoiceId)) : -1;
      if (idx < 0 && prevEngineVal) {
        idx = opts.findIndex(o => o.value === prevEngineVal);
      }
      if (idx >= 0) sel.selectedIndex = idx;
    };

    if (phoneSel) {
      phoneSel.innerHTML = optionsHtml;
      restoreVoiceSelection(phoneSel, curPhoneVoiceId, curPhoneVal);
      const pLang = document.getElementById('phone-call-language')?.value || 'en-US';
      if (typeof languageEngineSync !== 'undefined') {
        languageEngineSync.syncFromLanguage(pLang, phoneSel);
      }
      const badge = document.getElementById('phone-tts-badge');
      const selOpt = phoneSel.selectedOptions?.[0];
      const chosenV = this.voices.find(v => String(v.id) === String(selOpt?.dataset?.voiceId)) || activeVoice;
      if (badge && chosenV) badge.textContent = `${(chosenV.engine || 'f5tts').toUpperCase()} Active`;
    }

    if (simSel) {
      simSel.innerHTML = optionsHtml;
      restoreVoiceSelection(simSel, curSimVoiceId, curSimVal);
      const sLang = state.selectedLanguage || document.getElementById('sim-language')?.value || 'en-US';
      if (typeof languageEngineSync !== 'undefined') {
        languageEngineSync.syncFromLanguage(sLang, simSel);
      }
      const badge = document.getElementById('sim-tts-badge');
      const selOpt = simSel.selectedOptions?.[0];
      const chosenV = this.voices.find(v => String(v.id) === String(selOpt?.dataset?.voiceId)) || activeVoice;
      if (badge && chosenV) badge.textContent = `${(chosenV.engine || 'f5tts').toUpperCase()} Active`;

      const modelTag = document.getElementById('sim-model-tag');
      if (modelTag && chosenV) {
        const shortName = (chosenV.name || '').split('(')[0].trim() || (chosenV.engine || 'F5-TTS').toUpperCase();
        modelTag.innerHTML = `<i data-lucide="cpu"></i> Groq LLaMA / ${escapeHtml(shortName)}`;
        lucide.createIcons({ nodes: [modelTag] });
      }

      const prevBtn = document.getElementById('btn-sim-preview-prewarm');
      if (prevBtn && chosenV) {
        prevBtn.dataset.voiceId = String(chosenV.id || '');
        if (chosenV.preview_url) {
          prevBtn.dataset.url = chosenV.preview_url;
          prevBtn.style.display = 'inline-flex';
        }
      }
    }
  }
};

// Backward-compatibility alias
const voiceStudio = {
  checkStatus: () => voicesManager.loadVoices(),
  setFile: (f) => voicesManager.setFile(f),
  testVoice: () => voicesManager.computeVoice(),
};

/* ─── History Module ────────────────────────────────────────────── */
const history_ = {
  allCalls: [],

  render(calls) {
    history_.allCalls = calls;
    history_.filter();
  },

  filter(query) {
    const q = (query !== undefined ? query : (document.getElementById('history-search')?.value || '')).toLowerCase();
    const outcome = document.getElementById('history-filter-outcome')?.value || '';
    const minScore = parseInt(document.getElementById('history-filter-score')?.value) || 0;
    const contactMap = Object.fromEntries(state.contacts.map(c => [c.id, c.name]));
    const filtered = history_.allCalls.filter(c => {
      const name = (c.contact_name || contactMap[c.contact_id] || '').toLowerCase();
      const textMatch = !q || name.includes(q)
              || (c.outcome   || '').toLowerCase().includes(q)
              || (c.sentiment || '').toLowerCase().includes(q)
              || (c.summary   || '').toLowerCase().includes(q);
      const outcomeMatch = !outcome || (c.outcome || '') === outcome;
      const scoreMatch = !minScore || (c.lead_score || 0) >= minScore;
      return textMatch && outcomeMatch && scoreMatch;
    });
    history_._renderTable(filtered, contactMap);
  },

  exportCsv() {
    const outcome = document.getElementById('history-filter-outcome')?.value || '';
    const minScore = document.getElementById('history-filter-score')?.value || '';
    let url = `${api.base.replace(/\/$/, '')}/api/calls/export`;
    const params = [];
    if (outcome) params.push(`outcome=${encodeURIComponent(outcome)}`);
    if (minScore) params.push(`min_score=${encodeURIComponent(minScore)}`);
    if (params.length) url += '?' + params.join('&');
    const a = document.createElement('a');
    a.href = url;
    a.download = 'vocalyx_calls.csv';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    toast.success('Downloading call history CSV...');
  },

  _renderTable(calls, contactMap) {
    const tbody = document.getElementById('history-tbody');
    if (!calls.length) {
      tbody.innerHTML = `<tr><td colspan="6" class="empty-row">No calls found</td></tr>`;
      return;
    }
    const sorted = [...calls].sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
    tbody.innerHTML = sorted.map(c => `
      <tr>
        <td style="font-size:0.75rem;color:var(--text-muted)">${formatDate(c.created_at)}</td>
        <td>${escapeHtml(c.contact_name || contactMap[c.contact_id] || `#${c.contact_id}`)}</td>
        <td>${scoreBadge(c.lead_score)}</td>
        <td>${sentimentBadge(c.sentiment)}</td>
        <td>${outcomeBadge(c.outcome)}</td>
        <td>
          <button class="btn btn-outline btn-sm btn-view-detail" data-id="${c.id}">
            <i data-lucide="eye"></i> View
          </button>
        </td>
      </tr>
    `).join('');
    lucide.createIcons({ nodes: [tbody] });

    tbody.querySelectorAll('.btn-view-detail').forEach(btn => {
      btn.addEventListener('click', () => {
        const call = sorted.find(c => c.id == btn.dataset.id);
        if (call) history_.showDetail(call, contactMap);
      });
    });
  },

  showDetail(call, contactMap) {
    const name = contactMap[call.contact_id] || `Contact #${call.contact_id}`;
    document.getElementById('detail-badges').innerHTML = `
      ${scoreBadge(call.lead_score)}
      ${sentimentBadge(call.sentiment)}
      ${outcomeBadge(call.outcome)}
      <span class="badge badge-grey">${escapeHtml(name)}</span>
      <span class="badge badge-grey">${formatDate(call.created_at)}</span>
    `;
    document.getElementById('detail-transcript').textContent = call.transcript || 'No transcript available.';
    document.getElementById('detail-reasoning').textContent  = call.lead_score_reasoning || '—';
    document.getElementById('detail-summary').textContent    = call.summary || '—';
    document.getElementById('modal-call-detail').style.display = 'flex';
  },
};

/* ─── Contact Modal ─────────────────────────────────────────────── */
const contactModal = {
  open() {
    ['contact-name', 'contact-phone', 'contact-notes'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.value = '';
    });
    document.getElementById('modal-contact').style.display = 'flex';
    setTimeout(() => document.getElementById('contact-name')?.focus(), 100);
  },
  close() {
    document.getElementById('modal-contact').style.display = 'none';
  },
  async save() {
    const name  = document.getElementById('contact-name').value.trim();
    const phone = document.getElementById('contact-phone').value.trim();
    const notes = document.getElementById('contact-notes').value.trim();
    const preferred_language = document.getElementById('contact-language')?.value || 'en-US';

    if (!name)  { toast.info('Name is required.'); return; }
    if (!phone) { toast.info('Phone is required.'); return; }

    const btn = document.getElementById('modal-contact-save');
    btn.disabled = true;
    try {
      await api.createContact({ name, phone_number: phone, notes, preferred_language });
      toast.success(`Contact "${name}" added!`);
      contactModal.close();
      ui.loadContacts();
    } catch (e) {
      toast.error(`Save failed: ${e.message}`);
    } finally {
      btn.disabled = false;
    }
  },
};

/* ─── Settings Module ───────────────────────────────────────────── */
const settings = {
  async connectBackend() {
    const inp = document.getElementById('backend-url-input');
    const url = inp?.value.trim();
    if (!url) { toast.info('Please enter a URL.'); return; }

    const btn = document.getElementById('btn-connect-backend');
    btn.disabled = true;
    btn.textContent = 'Connecting…';

    const ok = await checkBackendHealth(url);
    if (ok) {
      localStorage.setItem(LS_KEY, url);
      api.base = url;
      toast.success('Backend connected!');
    } else {
      toast.error('Could not reach backend. Verify your Hugging Face Space is active.');
    }

    btn.disabled = false;
    btn.innerHTML = `<i data-lucide="plug-zap"></i> Connect →`;
    lucide.createIcons({ nodes: [btn] });
  },
};

/* ─── Twilio Telephony Manager ──────────────────────────────────── */
const twilioManager = {

  async loadConfig() {
    if (!state.backendOk) return;
    try {
      const savedLocal = localStorage.getItem('vocalyx_twilio_config');
      if (savedLocal) {
        try {
          const loc = JSON.parse(savedLocal);
          const sidInp = document.getElementById('twilio-sid-input');
          const tokenInp = document.getElementById('twilio-token-input');
          const phoneInp = document.getElementById('twilio-phone-input');
          if (sidInp && !sidInp.value && loc.sid) sidInp.value = loc.sid;
          if (tokenInp && !tokenInp.value && loc.token) tokenInp.value = loc.token;
          if (phoneInp && !phoneInp.value && loc.phone) phoneInp.value = loc.phone;
        } catch {}
      }

      const cfg = await api.getTwilioConfig();
      state.twilioConfig = cfg || {};
      twilioManager.updateUI();
    } catch (err) {
      console.warn('[Twilio] Config fetch:', err);
    }
  },

  updateUI() {
    const cfg = state.twilioConfig || {};
    const isConfigured = !!cfg.configured;

    // Settings badge & dot
    const dot   = document.getElementById('twilio-settings-dot');
    const label = document.getElementById('twilio-settings-label');
    if (dot && label) {
      dot.className = 'conn-dot ' + (isConfigured ? 'connected' : 'disconnected');
      label.textContent = isConfigured ? `Connected (${cfg.phone_number || 'Active'})` : 'Not Configured';
    }

    // Phone section status & badges
    const phoneDot = document.getElementById('phone-twilio-conn-dot');
    const phoneStatusText = document.getElementById('phone-twilio-status-text');
    const phoneLineNumber = document.getElementById('phone-line-number');
    const twilioSimStatus = document.getElementById('twilio-sim-status');

    if (phoneDot) phoneDot.className = 'conn-dot ' + (isConfigured ? 'connected' : 'disconnected');
    if (phoneStatusText) phoneStatusText.textContent = isConfigured ? 'Twilio Line Connected' : 'Twilio Line Disconnected';
    if (phoneLineNumber) phoneLineNumber.textContent = isConfigured ? `Twilio Caller ID: ${cfg.phone_number || 'Active'}` : 'Twilio Line: Not Configured';
    if (twilioSimStatus) {
      twilioSimStatus.className = 'badge ' + (isConfigured ? 'badge-lime' : 'badge-grey');
      twilioSimStatus.textContent = isConfigured ? (cfg.phone_number || 'Active') : 'Not Configured';
    }

    // Settings inputs
    const sidInp      = document.getElementById('twilio-sid-input');
    const phoneInp    = document.getElementById('twilio-phone-input');
    const webhookDisp = document.getElementById('twilio-webhook-display');
    if (sidInp && !sidInp.value && cfg.account_sid) {
      if (!cfg.account_sid.includes('...')) {
        sidInp.value = cfg.account_sid;
      } else {
        sidInp.placeholder = cfg.account_sid;
      }
    }
    if (phoneInp && !phoneInp.value && cfg.phone_number) {
      phoneInp.value = cfg.phone_number;
    }
    if (webhookDisp && cfg.webhook_url) {
      webhookDisp.value = cfg.webhook_url;
    }
    const activeVoice = (cfg.voice_engine || 'f5tts').toLowerCase();
    twilioManager.updateEngineBadge(activeVoice);
  },

  updateEngineBadge(engine) {
    const activeEngine = (engine || 'f5tts').toLowerCase();
    const phoneSelect = document.getElementById('phone-tts-engine');
    const settingsSelect = document.getElementById('twilio-voice-select');
    if (phoneSelect && phoneSelect.value !== activeEngine) phoneSelect.value = activeEngine;
    if (settingsSelect && settingsSelect.value !== activeEngine) settingsSelect.value = activeEngine;

    const badge = document.getElementById('phone-tts-badge');
    const hint = document.getElementById('phone-tts-engine-hint');
    const prewarmBox = document.querySelector('.voice-prewarm-box');
    const label = document.getElementById('btn-prewarm-label');

    const engineMap = {
      f5tts: {
        badge: 'F5-TTS (Flow-Matching)',
        hint: 'Alex will speak using F5-TTS cloned voice synthesized into GPU memory.',
        isCloned: true,
      },
      luxtts: {
        badge: 'LuxTTS (Diffusion ~0.2s)',
        hint: 'Alex will speak using ultra-fast LuxTTS diffusion cloned voice (~0.2s generation).',
        isCloned: true,
      },
      polly: {
        badge: 'Polly Matthew (Twilio)',
        hint: 'Alex will speak using Amazon Polly Matthew, generated natively by Twilio (zero GPU latency).',
        isCloned: false,
      }
    };

    const info = engineMap[activeEngine] || engineMap.f5tts;
    if (badge) badge.textContent = info.badge;
    if (hint) hint.textContent = info.hint;
    if (prewarmBox) {
      if (!info.isCloned) {
        prewarmBox.style.display = 'none';
      } else {
        prewarmBox.style.display = 'block';
        if (label) label.textContent = `Ready ${activeEngine.toUpperCase()} Voice`;
      }
    }
  },

  async saveConfig() {
    let sid   = document.getElementById('twilio-sid-input')?.value.trim();
    const token = document.getElementById('twilio-token-input')?.value.trim();
    const phone = document.getElementById('twilio-phone-input')?.value.trim();
    const voiceEngine = document.getElementById('phone-tts-engine')?.value || document.getElementById('twilio-voice-select')?.value || 'f5tts';

    if (!sid || sid.includes('...')) {
      toast.info('Please paste your full 34-character Twilio Account SID (starts with AC) from twilio.com/console.');
      return;
    }
    if (!token) {
      toast.info('Please enter your 32-character Twilio Auth Token from twilio.com/console.');
      return;
    }
    if (!phone) {
      toast.info('Please enter your Twilio Phone Number (e.g. +15550001234).');
      return;
    }

    try {
      localStorage.setItem('vocalyx_twilio_config', JSON.stringify({ sid, token, phone }));
    } catch {}

    const btn = document.getElementById('btn-save-twilio');
    if (btn) { btn.disabled = true; btn.textContent = 'Verifying with Twilio…'; }

    try {
      const res = await api.updateTwilioConfig({
        account_sid: sid,
        auth_token: token,
        phone_number: phone,
        public_base_url: api.base,
        voice_engine: voiceEngine,
      });

      if (res && res.verification && res.verification.ok) {
        toast.success(`✓ Twilio verified! Account: ${res.verification.account_name || 'Active'}`);
      } else if (res && res.verification && res.verification.error) {
        toast.error(`Twilio error: ${res.verification.error}`);
      } else {
        toast.success('Twilio settings saved.');
      }
      await twilioManager.loadConfig();
    } catch (e) {
      toast.error(`Save Twilio failed: ${e.message}`);
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = `<i data-lucide="check-circle"></i> Save & Verify Twilio`;
        lucide.createIcons({ nodes: [btn] });
      }
    }
  },

  async testConnection() {
    toast.info('Testing Twilio connection...');
    try {
      const res = await api.testTwilio();
      if (res.ok) {
        toast.success(`✓ Connected! Account: ${res.account_name} (${res.status})`);
      } else {
        toast.error(`Twilio check failed: ${res.error || 'Invalid credentials'}`);
      }
      await twilioManager.loadConfig();
    } catch (e) {
      toast.error(`Twilio test error: ${e.message}`);
    }
  },

  async dial(toNumber = null) {
    if (!state.backendOk) {
      toast.error('Backend is not connected. Connect in Settings first.');
      return;
    }

    const number = toNumber || document.getElementById('twilio-dial-number')?.value.trim();
    if (!number) {
      toast.info('Please enter a destination phone number (with + country code).');
      return;
    }

    if (!state.twilioConfig?.configured) {
      toast.info('Twilio is not configured yet. Go to Settings to enter your credentials.');
      ui.showSection('settings');
      return;
    }

    const contactId = document.getElementById('phone-contact-select')?.value || simulator.getActiveContactId();
    const mode = 'outbound';
    const voiceEngine = document.getElementById('phone-tts-engine')?.value || document.getElementById('twilio-voice-select')?.value || 'f5tts';
    const callLang = document.getElementById('phone-call-language')?.value || state.selectedLanguage || 'en-US';

    if (voiceEngine !== 'polly' && typeof voicePrewarmManager !== 'undefined' && !voicePrewarmManager.isReady) {
      toast.info(`Initiating call with ${voiceEngine.toUpperCase()}... Tip: Click "Ready ${voiceEngine.toUpperCase()} Voice" for instant 0.0s greeting.`);
    } else {
      toast.info(`Dialing real phone: ${number} via ${voiceEngine.toUpperCase()}...`);
    }
    try {
      const res = await api.dialPhone({
        to_number: number,
        contact_id: contactId ? parseInt(contactId) : null,
        mode: mode,
        public_url: api.base,
        voice_engine: voiceEngine,
        language: callLang,
      });

      if (res && res.call_sid) {
        toast.success(`Phone call initiated! Calling ${number}...`);
        twilioManager.startActiveCall(res.call_sid, number);
      } else {
        toast.error('Failed to initiate call.');
      }
    } catch (e) {
      toast.error(`Dial error: ${e.message}`);
    }
  },

  startActiveCall(callSid, targetNumber) {
    state.activeTwilioCall = {
      callSid,
      targetNumber,
      startTime: Date.now(),
      status: 'initiated',
    };

    const box          = document.getElementById('twilio-in-call-box');
    const statusEl     = document.getElementById('twilio-active-status');
    const targetEl     = document.getElementById('twilio-active-target');
    const timerEl      = document.getElementById('twilio-active-timer');
    const streamStatus = document.getElementById('phone-stream-status');

    if (box) box.style.display = 'block';
    if (statusEl) statusEl.textContent = 'Calling / Ringing...';
    if (targetEl) targetEl.textContent = `Dialing ${targetNumber}`;
    if (timerEl) timerEl.textContent = '00:00';
    if (streamStatus) {
      streamStatus.className = 'badge badge-lime';
      streamStatus.textContent = `Calling ${targetNumber}`;
    }

    // Reset phone transcript & hide previous analysis
    const phoneLog = document.getElementById('phone-conversation-log');
    if (phoneLog) {
      phoneLog.innerHTML = `<div class="conv-placeholder" id="phone-conv-placeholder">Call placed to ${escapeHtml(targetNumber)}. Awaiting answer...</div>`;
    }
    const phoneCard = document.getElementById('phone-analysis-card');
    if (phoneCard) phoneCard.style.display = 'none';

    // Timer
    state.twilioTimerSeconds = 0;
    if (state.twilioTimerInterval) clearInterval(state.twilioTimerInterval);
    state.twilioTimerInterval = setInterval(() => {
      state.twilioTimerSeconds++;
      const m = String(Math.floor(state.twilioTimerSeconds / 60)).padStart(2, '0');
      const s = String(state.twilioTimerSeconds % 60).padStart(2, '0');
      if (timerEl) timerEl.textContent = `${m}:${s}`;
    }, 1000);

    // Poll live status & transcript
    if (state.twilioPollInterval) clearInterval(state.twilioPollInterval);
    state.twilioPollInterval = setInterval(async () => {
      try {
        const call = await api.getActivePhoneCall(callSid);
        if (call && call.status) {
          if (statusEl) statusEl.textContent = `Status: ${call.status}`;
          if (streamStatus) streamStatus.textContent = `Call: ${call.status}`;

          // Sync into dedicated phone conversation log
          if (call.transcript && Array.isArray(call.transcript) && call.transcript.length) {
            if (phoneLog) {
              phoneLog.innerHTML = call.transcript.map(m => `
                <div class="conv-bubble ${m.role === 'user' ? 'user' : 'agent'}" style="margin-bottom:8px;">
                  <div class="conv-bubble-role">${m.role === 'user' ? '📞 Caller' : '👤 Alex (Cloned Voice)'}</div>
                  <div class="conv-bubble-text">${escapeHtml(m.text)}</div>
                </div>
              `).join('');
              phoneLog.scrollTop = phoneLog.scrollHeight;
            }
          }

          if (['completed', 'busy', 'no-answer', 'failed', 'canceled'].includes(call.status.toLowerCase())) {
            toast.info(`Phone call ended (${call.status}).`);
            twilioManager.endActiveCall();

            if (call.analysis) {
              twilioManager.showPhoneAnalysis(call.analysis);
            }
            ui.loadDashboard();
            ui.loadHistory();
          }
        }
      } catch {}
    }, 2000);
  },

  showPhoneAnalysis(analysis) {
    const card = document.getElementById('phone-analysis-card');
    if (!card) return;
    card.style.display = 'block';

    const score = analysis.lead_score || 0;
    const circumference = 314;
    const offset = circumference - (score / 100) * circumference;
    const fillEl = document.getElementById('phone-score-fill-circle');
    if (fillEl) {
      fillEl.style.strokeDashoffset = offset;
      fillEl.style.stroke = score >= 70 ? 'var(--accent-dark)' : score >= 40 ? 'var(--yellow)' : 'var(--red)';
    }
    const scoreEl = document.getElementById('phone-score-number');
    if (scoreEl) scoreEl.textContent = score;

    const sentEl = document.getElementById('phone-analysis-sentiment');
    if (sentEl) sentEl.innerHTML = sentimentBadge(analysis.sentiment);

    const outEl = document.getElementById('phone-analysis-outcome');
    if (outEl) outEl.innerHTML = outcomeBadge(analysis.outcome);

    renderAlertStatusRows(analysis, 'phone');

    const reasEl = document.getElementById('phone-analysis-reasoning');
    if (reasEl) reasEl.textContent = analysis.lead_score_reasoning || '—';

    const sumEl = document.getElementById('phone-analysis-summary');
    if (sumEl) sumEl.textContent = analysis.summary || '—';
  },

  async hangup() {
    const callSid = state.activeTwilioCall?.callSid;
    if (!callSid) {
      twilioManager.endActiveCall();
      return;
    }
    toast.info('Hanging up phone call...');
    try {
      await api.hangupPhone(callSid);
      toast.success('Call ended.');
    } catch (e) {
      console.warn('[Twilio Hangup]', e);
    } finally {
      twilioManager.endActiveCall();
      ui.loadHistory();
    }
  },

  endActiveCall() {
    if (state.twilioPollInterval) {
      clearInterval(state.twilioPollInterval);
      state.twilioPollInterval = null;
    }
    if (state.twilioTimerInterval) {
      clearInterval(state.twilioTimerInterval);
      state.twilioTimerInterval = null;
    }
    state.activeTwilioCall = null;
    const box = document.getElementById('twilio-in-call-box');
    if (box) box.style.display = 'none';
    const streamStatus = document.getElementById('phone-stream-status');
    if (streamStatus) {
      streamStatus.className = 'badge badge-grey';
      streamStatus.textContent = 'Call Finished';
    }
  },
};

/* ─── Message Alerts Manager (WhatsApp, SMS, Telegram) ──────────── */
const alertsManager = {
  config: null,

  async loadConfig() {
    if (!state.backendOk) return;
    try {
      const cfg = await api.getAlertsConfig();
      if (!cfg) return;
      alertsManager.config = cfg;
      alertsManager.updateUI(cfg);
    } catch (err) {
      console.warn('[Alerts] Load config error:', err);
    }
  },

  updateUI(cfg) {
    if (!cfg) cfg = alertsManager.config || {};
    const twReady = !!cfg.twilio_configured;
    const twPhone = cfg.twilio_phone_number || '';

    // 1. WhatsApp UI
    const wa = cfg.whatsapp || {};
    const waEnabled = document.getElementById('alert-wa-enabled');
    const waTo = document.getElementById('alert-wa-to');
    const waFrom = document.getElementById('alert-wa-from');
    const waBadge = document.getElementById('wa-status-badge');
    const waWarning = document.getElementById('wa-twilio-warning');

    if (waEnabled) waEnabled.checked = !!wa.enabled;
    if (waTo && !waTo.value && wa.to_phone) waTo.value = wa.to_phone;
    if (waFrom) waFrom.value = wa.from_phone || 'whatsapp:+14155238886';

    if (waWarning) waWarning.style.display = twReady ? 'none' : 'block';
    if (waBadge) {
      if (!twReady) {
        waBadge.innerHTML = `<span class="badge" style="background:rgba(239,68,68,0.15); color:#f87171;"><i data-lucide="alert-circle"></i> Twilio Disconnected</span>`;
      } else if (wa.enabled && wa.to_phone) {
        waBadge.innerHTML = `<span class="badge badge-lime"><i data-lucide="check-circle"></i> Active</span>`;
      } else {
        waBadge.innerHTML = `<span class="badge badge-gray">Twilio Ready</span>`;
      }
    }

    // 2. SMS UI
    const sms = cfg.sms || {};
    const smsEnabled = document.getElementById('alert-sms-enabled');
    const smsTo = document.getElementById('alert-sms-to');
    const smsFromDisplay = document.getElementById('alert-sms-from-display');
    const smsBadge = document.getElementById('sms-status-badge');
    const smsWarning = document.getElementById('sms-twilio-warning');

    if (smsEnabled) smsEnabled.checked = !!sms.enabled;
    if (smsTo && !smsTo.value && sms.to_phone) smsTo.value = sms.to_phone;
    if (smsFromDisplay) smsFromDisplay.value = twPhone || 'Not configured in Settings';

    if (smsWarning) smsWarning.style.display = twReady ? 'none' : 'block';
    if (smsBadge) {
      if (!twReady) {
        smsBadge.innerHTML = `<span class="badge" style="background:rgba(239,68,68,0.15); color:#f87171;"><i data-lucide="alert-circle"></i> Twilio Disconnected</span>`;
      } else if (sms.enabled && sms.to_phone) {
        smsBadge.innerHTML = `<span class="badge badge-lime"><i data-lucide="check-circle"></i> Active</span>`;
      } else {
        smsBadge.innerHTML = `<span class="badge badge-gray">Twilio Ready</span>`;
      }
    }

    // 3. Telegram UI
    const tg = cfg.telegram || {};
    const tgEnabled = document.getElementById('alert-tg-enabled');
    const tgToken = document.getElementById('alert-tg-token');
    const tgChatId = document.getElementById('alert-tg-chatid');
    const tgBadge = document.getElementById('tg-status-badge');

    if (tgEnabled) tgEnabled.checked = tg.enabled !== false;
    if (tgToken && !tgToken.value && tg.bot_token) tgToken.value = tg.bot_token;
    if (tgChatId && !tgChatId.value && tg.chat_id) tgChatId.value = tg.chat_id;

    if (tgBadge) {
      if (tg.ready && tg.enabled !== false) {
        tgBadge.innerHTML = `<span class="badge badge-lime"><i data-lucide="check-circle"></i> Active</span>`;
      } else if (tg.ready) {
        tgBadge.innerHTML = `<span class="badge badge-gray">Configured (Disabled)</span>`;
      } else {
        tgBadge.innerHTML = `<span class="badge" style="background:rgba(239,68,68,0.15); color:#f87171;"><i data-lucide="alert-circle"></i> Not Configured</span>`;
      }
    }

    lucide.createIcons();
  },

  async saveWhatsApp() {
    const toPhone = document.getElementById('alert-wa-to')?.value.trim();
    const fromPhone = document.getElementById('alert-wa-from')?.value.trim() || 'whatsapp:+14155238886';
    const enabled = document.getElementById('alert-wa-enabled')?.checked || false;

    if (enabled && !toPhone) {
      toast.info('Please enter your recipient WhatsApp number.');
      return;
    }

    const btn = document.getElementById('btn-save-wa-alert');
    if (btn) btn.disabled = true;
    try {
      await api.updateAlertsConfig({
        whatsapp: { enabled, to_phone: toPhone, from_phone: fromPhone }
      });
      toast.success('WhatsApp alert settings saved!');
      await alertsManager.loadConfig();
    } catch (e) {
      toast.error(`Save WhatsApp failed: ${e.message}`);
    } finally {
      if (btn) btn.disabled = false;
    }
  },

  async testWhatsApp() {
    const toPhone = document.getElementById('alert-wa-to')?.value.trim();
    const fromPhone = document.getElementById('alert-wa-from')?.value.trim() || 'whatsapp:+14155238886';
    if (!toPhone) {
      toast.info('Please enter a destination WhatsApp number before testing.');
      return;
    }
    const btn = document.getElementById('btn-test-wa-alert');
    if (btn) { btn.disabled = true; btn.textContent = 'Sending…'; }
    try {
      const res = await api.testAlert({
        channel: 'whatsapp',
        to_phone: toPhone,
        from_phone: fromPhone,
      });
      if (res && res.ok) {
        toast.success(`✓ WhatsApp alert sent! ${res.result || ''}`);
      } else {
        toast.error(`WhatsApp test failed: ${res.result || 'Unknown error'}`);
      }
    } catch (e) {
      toast.error(`WhatsApp test error: ${e.message}`);
    } finally {
      if (btn) { btn.disabled = false; btn.innerHTML = `<i data-lucide="send"></i> Test WhatsApp`; lucide.createIcons({ nodes: [btn] }); }
    }
  },

  async saveSMS() {
    const toPhone = document.getElementById('alert-sms-to')?.value.trim();
    const enabled = document.getElementById('alert-sms-enabled')?.checked || false;

    if (enabled && !toPhone) {
      toast.info('Please enter your recipient phone number.');
      return;
    }

    const btn = document.getElementById('btn-save-sms-alert');
    if (btn) btn.disabled = true;
    try {
      await api.updateAlertsConfig({
        sms: { enabled, to_phone: toPhone }
      });
      toast.success('SMS alert settings saved!');
      await alertsManager.loadConfig();
    } catch (e) {
      toast.error(`Save SMS failed: ${e.message}`);
    } finally {
      if (btn) btn.disabled = false;
    }
  },

  async testSMS() {
    const toPhone = document.getElementById('alert-sms-to')?.value.trim();
    if (!toPhone) {
      toast.info('Please enter a destination mobile phone number before testing.');
      return;
    }
    const btn = document.getElementById('btn-test-sms-alert');
    if (btn) { btn.disabled = true; btn.textContent = 'Sending…'; }
    try {
      const res = await api.testAlert({
        channel: 'sms',
        to_phone: toPhone,
      });
      if (res && res.ok) {
        toast.success(`✓ SMS text alert sent! ${res.result || ''}`);
      } else {
        toast.error(`SMS test failed: ${res.result || 'Unknown error'}`);
      }
    } catch (e) {
      toast.error(`SMS test error: ${e.message}`);
    } finally {
      if (btn) { btn.disabled = false; btn.innerHTML = `<i data-lucide="send"></i> Test SMS`; lucide.createIcons({ nodes: [btn] }); }
    }
  },

  async saveTelegram() {
    const token = document.getElementById('alert-tg-token')?.value.trim();
    const chatId = document.getElementById('alert-tg-chatid')?.value.trim();
    const enabled = document.getElementById('alert-tg-enabled')?.checked || false;

    if (enabled && (!token || !chatId)) {
      toast.info('Please enter your Telegram Bot Token and Chat ID.');
      return;
    }

    const btn = document.getElementById('btn-save-tg-alert');
    if (btn) btn.disabled = true;
    try {
      await api.updateAlertsConfig({
        telegram: { enabled, bot_token: token, chat_id: chatId }
      });
      toast.success('Telegram alert settings saved!');
      await alertsManager.loadConfig();
    } catch (e) {
      toast.error(`Save Telegram failed: ${e.message}`);
    } finally {
      if (btn) btn.disabled = false;
    }
  },

  async testTelegram() {
    const token = document.getElementById('alert-tg-token')?.value.trim();
    const chatId = document.getElementById('alert-tg-chatid')?.value.trim();
    if (!token || !chatId) {
      toast.info('Please enter your Telegram Bot Token and Chat ID before testing.');
      return;
    }
    const btn = document.getElementById('btn-test-tg-alert');
    if (btn) { btn.disabled = true; btn.textContent = 'Sending…'; }
    try {
      const res = await api.testAlert({
        channel: 'telegram',
        bot_token: token,
        chat_id: chatId,
      });
      if (res && res.ok) {
        toast.success(`✓ Telegram test alert delivered!`);
      } else {
        toast.error(`Telegram test failed: ${res.result || 'Unknown error'}`);
      }
    } catch (e) {
      toast.error(`Telegram test error: ${e.message}`);
    } finally {
      if (btn) { btn.disabled = false; btn.innerHTML = `<i data-lucide="send"></i> Test Telegram`; lucide.createIcons({ nodes: [btn] }); }
    }
  },
};

/* ─── Cloned Voice Engine Pre-Warm Manager ───────────────────────── */
const voicePrewarmManager = {
  isReady: false,
  greetingUrl: null,
  activeVoiceId: null,

  async checkStatus() {
    const badge = document.getElementById('voice-prewarm-badge');
    const label = document.getElementById('btn-prewarm-label');
    const prevBtn = document.getElementById('btn-preview-greeting');
    const hint = document.getElementById('voice-prewarm-hint');
    const simPrevBtn = document.getElementById('btn-sim-preview-prewarm');
    if (!badge) return;

    try {
      const res = await api.getPrewarmStatus();
      if (res && res.ready) {
        this.isReady = true;
        this.greetingUrl = res.greeting_url;
        this.activeVoiceId = res.active_voice_id ? String(res.active_voice_id) : this.activeVoiceId;
        badge.className = 'badge badge-lime';
        badge.textContent = '🟢 Ready (0.0s)';
        if (label) label.textContent = 'Re-Warm Voice';
        if (prevBtn) prevBtn.style.display = 'inline-flex';
        if (simPrevBtn) {
          simPrevBtn.style.display = 'inline-flex';
          if (res.greeting_url) simPrevBtn.dataset.url = res.greeting_url;
          if (this.activeVoiceId) simPrevBtn.dataset.voiceId = this.activeVoiceId;
        }
        const vLabel = res.active_voice_name ? `${escapeHtml(res.active_voice_name)} greeting` : 'Cloned voice greeting';
        if (hint) hint.innerHTML = `<span style="color:var(--color-lime,#c5f82a);">✓ ${vLabel} is ready on disk. Phone call will connect with 0.0s delay!</span>`;
      } else {
        this.isReady = false;
        badge.className = 'badge badge-grey';
        badge.textContent = 'Not Ready';
        if (label) label.textContent = 'Ready Cloned Voice';
        if (prevBtn) prevBtn.style.display = 'none';
        if (hint) hint.textContent = 'Pre-computes cloned voice weights into GPU memory so your call connects with 0 delay.';
      }
    } catch (e) {
      if (badge) {
        badge.className = 'badge badge-grey';
        badge.textContent = 'Offline / Standby';
      }
    }
    if (typeof lucide !== 'undefined' && lucide.createIcons) lucide.createIcons();
  },

  async prewarm() {
    const phoneSel = document.getElementById('phone-tts-engine');
    const activeEngine = phoneSel?.value || 'f5tts';
    const voiceId = phoneSel?.selectedOptions?.[0]?.dataset?.voiceId || null;
    const badge = document.getElementById('voice-prewarm-badge');
    const btn = document.getElementById('btn-prewarm-voice');
    const label = document.getElementById('btn-prewarm-label');
    const prevBtn = document.getElementById('btn-preview-greeting');
    const hint = document.getElementById('voice-prewarm-hint');

    if (activeEngine === 'polly') {
      toast.info('Amazon Polly Matthew requires no pre-warming — native Twilio telephony is always ready.');
      return;
    }

    if (btn) btn.disabled = true;
    if (badge) {
      badge.className = 'badge badge-yellow';
      badge.textContent = `⏳ Warming ${activeEngine.toUpperCase()}...`;
    }
    if (hint) hint.textContent = `Allocating GPU and pre-computing ${activeEngine.toUpperCase()} voice conditioning...`;
    toast.info(`Warming up ${activeEngine.toUpperCase()} and generating cloned voice greeting...`);

    // Poll status every 2.5s while the model is warming up
    let completedViaPoll = false;
    const pollInterval = setInterval(async () => {
      try {
        const s = await api.getPrewarmStatus();
        if (s && s.ready) {
          completedViaPoll = true;
          this.isReady = true;
          this.greetingUrl = s.greeting_url;
          if (badge) {
            badge.className = 'badge badge-lime';
            badge.textContent = '🟢 Ready (0.0s)';
          }
          if (label) label.textContent = `Re-Warm ${activeEngine.toUpperCase()}`;
          if (prevBtn) prevBtn.style.display = 'inline-flex';
          if (hint) hint.innerHTML = `<span style="color:var(--color-lime,#c5f82a);">✓ ${activeEngine.toUpperCase()} cloned voice ready! Saved to disk. Ready to call.</span>`;
        }
      } catch {}
    }, 2500);

    try {
      const res = await api.prewarmVoice(activeEngine, voiceId);
      clearInterval(pollInterval);
      if (res && res.ready) {
        this.isReady = true;
        this.greetingUrl = res.greeting_url;
        this.activeVoiceId = res.voice_id ? String(res.voice_id) : voiceId;
        if (badge) {
          badge.className = 'badge badge-lime';
          badge.textContent = '🟢 Ready (0.0s)';
        }
        if (label) label.textContent = `Re-Warm ${activeEngine.toUpperCase()}`;
        if (prevBtn) prevBtn.style.display = 'inline-flex';
        if (hint) hint.innerHTML = `<span style="color:var(--color-lime,#c5f82a);">✓ ${activeEngine.toUpperCase()} ready in ${res.elapsed_seconds}s! Ready to call.</span>`;
        toast.success(`Voice engine (${activeEngine.toUpperCase()}) ready! (${res.elapsed_seconds}s).`);
      } else if (!completedViaPoll) {
        throw new Error(res.message || 'Pre-warm failed');
      }
    } catch (e) {
      clearInterval(pollInterval);
      // Double check if backend finished despite network abort/timeout
      try {
        const s = await api.getPrewarmStatus();
        if (s && s.ready) {
          this.isReady = true;
          this.greetingUrl = s.greeting_url;
          if (badge) {
            badge.className = 'badge badge-lime';
            badge.textContent = '🟢 Ready (0.0s)';
          }
          if (label) label.textContent = 'Re-Warm Voice';
          if (prevBtn) prevBtn.style.display = 'inline-flex';
          if (hint) hint.innerHTML = '<span style="color:var(--color-lime,#c5f82a);">✓ Cloned voice ready! Saved to disk. Ready to call.</span>';
          toast.success('Voice engine ready! Saved to disk. Ready to call.');
          return;
        }
      } catch {}

      if (badge) {
        badge.className = 'badge badge-red';
        badge.textContent = 'Pre-Warm Failed';
      }
      if (hint) hint.textContent = `Error: ${e.message}`;
      toast.error(`Pre-warm error: ${e.message}`);
    } finally {
      clearInterval(pollInterval);
      if (btn) btn.disabled = false;
      if (typeof lucide !== 'undefined' && lucide.createIcons) lucide.createIcons();
    }
  },

  async preview() {
    const phoneSel = document.getElementById('phone-tts-engine');
    const selVoiceId = phoneSel?.selectedOptions?.[0]?.dataset?.voiceId || null;
    const matchedVoice = selVoiceId && typeof voicesManager !== 'undefined'
      ? (voicesManager.voices || []).find(v => String(v.id) === String(selVoiceId))
      : null;
    const rawUrl = (matchedVoice && String(selVoiceId) !== String(this.activeVoiceId) && matchedVoice.preview_url)
      ? matchedVoice.preview_url
      : (this.greetingUrl || matchedVoice?.preview_url);
    if (!rawUrl) {
      toast.info('No pre-warmed greeting available yet. Click "Ready Cloned Voice" to generate.');
      return;
    }
    toast.info('Loading voice greeting audio...');
    try {
      const baseFull = rawUrl.startsWith('http') ? rawUrl : `${api.base.replace(/\/$/, '')}${rawUrl}`;
      const fullUrl = `${baseFull}${baseFull.includes('?') ? '&' : '?'}t=${Date.now()}`;
      const blobUrl = await simulator.fetchAudioBlob(fullUrl);
      const audio = new Audio(blobUrl);
      audio.onended = () => URL.revokeObjectURL(blobUrl);
      audio.onerror = () => URL.revokeObjectURL(blobUrl);
      await audio.play();
      toast.success(`Playing ${matchedVoice?.name || 'pre-warmed voice'} greeting!`);
    } catch (e) {
      toast.error(`Audio playback note: ${e.message}`);
    }
  }
};

/* ─── Call Simulator Voice Re-Warm Manager ──────────────────────── */
const simPrewarm = {
  async prewarm() {
    const simSel = document.getElementById('sim-tts-engine');
    const engine = simSel?.value || 'f5tts';
    const selOpt = simSel?.selectedOptions?.[0];
    const voiceId = selOpt?.dataset?.voiceId || null;
    const btn = document.getElementById('btn-sim-prewarm');
    const label = document.getElementById('btn-sim-prewarm-label');
    const prevBtn = document.getElementById('btn-sim-preview-prewarm');
    const hint = document.getElementById('sim-prewarm-hint');

    if (btn) btn.disabled = true;
    if (label) label.textContent = `Warming ${engine.toUpperCase()}...`;
    if (hint) hint.textContent = `Allocating GPU memory and caching voice weights...`;
    toast.info(`Pre-warming selected voice (${engine.toUpperCase()}) for Call Simulator...`);

    try {
      const res = await api.prewarmVoice(engine, voiceId);
      if (res && res.ready) {
        voicePrewarmManager.isReady = true;
        voicePrewarmManager.greetingUrl = res.greeting_url || '/tts_output/prewarmed_greeting.wav';
        voicePrewarmManager.activeVoiceId = res.voice_id ? String(res.voice_id) : (voiceId ? String(voiceId) : null);
        if (label) label.textContent = `Re-Warm (Ready)`;
        if (prevBtn) {
          prevBtn.style.display = 'inline-flex';
          prevBtn.dataset.url = res.greeting_url || '/tts_output/prewarmed_greeting.wav';
          prevBtn.dataset.voiceId = voicePrewarmManager.activeVoiceId || '';
        }
        const vName = res.voice_name || selOpt?.textContent?.split('—')?.[0]?.trim() || engine.toUpperCase();
        if (hint) hint.innerHTML = `<span style="color:var(--color-lime,#c5f82a);">✓ ${escapeHtml(vName)} ready! Starting call plays with 0.0s delay.</span>`;
        toast.success(`✓ ${vName} pre-warmed and ready (${res.elapsed_seconds || '0.1'}s)!`);
      } else {
        throw new Error(res.message || 'Prewarm incomplete');
      }
    } catch (err) {
      toast.error(`Prewarm note: ${err.message}`);
      if (label) label.textContent = `Re-Warm Selected Voice`;
    } finally {
      if (btn) btn.disabled = false;
      if (typeof lucide !== 'undefined' && lucide.createIcons) lucide.createIcons();
    }
  },

  async preview() {
    const simSel = document.getElementById('sim-tts-engine');
    const selOpt = simSel?.selectedOptions?.[0];
    const selVoiceId = selOpt?.dataset?.voiceId || null;
    const selEngine = simSel?.value || 'f5tts';
    const matchedVoice = typeof voicesManager !== 'undefined'
      ? ((voicesManager.voices || []).find(v => selVoiceId && String(v.id) === String(selVoiceId))
        || (voicesManager.voices || []).find(v => v.engine === selEngine))
      : null;

    const prevBtn = document.getElementById('btn-sim-preview-prewarm');
    let rawUrl = null;
    if (prevBtn?.dataset?.url && (!selVoiceId || prevBtn.dataset.voiceId === String(selVoiceId))) {
      rawUrl = prevBtn.dataset.url;
    } else if (matchedVoice?.preview_url) {
      rawUrl = matchedVoice.preview_url;
    } else {
      rawUrl = voicePrewarmManager.greetingUrl || '/tts_output/prewarmed_greeting.wav';
    }

    toast.info(`Loading ${matchedVoice?.name || 'selected voice'} preview...`);
    try {
      const baseFull = rawUrl.startsWith('http') ? rawUrl : `${api.base.replace(/\/$/, '')}${rawUrl}`;
      const fullUrl = `${baseFull}${baseFull.includes('?') ? '&' : '?'}t=${Date.now()}`;
      const blobUrl = await simulator.fetchAudioBlob(fullUrl);
      const audio = new Audio(blobUrl);
      audio.onended = () => URL.revokeObjectURL(blobUrl);
      audio.onerror = () => URL.revokeObjectURL(blobUrl);
      await audio.play();
      toast.success(`Playing ${matchedVoice?.name || 'voice'} preview!`);
    } catch (e) {
      toast.error(`Playback note: ${e.message}`);
    }
  }
};


/* ─── Call Mode Switching ───────────────────────────────────────── */
function bindCallModeTabs() {
  const tabs = document.querySelectorAll('.mode-tab');
  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      if (state.callActive) return; // don't change during call
      tabs.forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      state.callMode = tab.dataset.mode;

      // Show/hide panels
      document.getElementById('panel-outbound').style.display   = (state.callMode === 'outbound') ? '' : 'none';
      document.getElementById('panel-inbound').style.display    = (state.callMode === 'inbound')  ? '' : 'none';
      document.getElementById('panel-marketing').style.display  = (state.callMode === 'marketing')? '' : 'none';

      // Reset caller match
      if (state.callMode !== 'inbound') {
        state.currentContact = null;
      }
    });
  });
}

/* ─── Event Bindings ────────────────────────────────────────────── */
function bindEvents() {
  // Sidebar nav
  document.querySelectorAll('.nav-item').forEach(el => {
    el.addEventListener('click', () => {
      ui.showSection(el.dataset.section);
      document.getElementById('sidebar').classList.remove('open');
    });
  });

  // Mobile menu
  document.getElementById('menu-toggle').addEventListener('click', () => {
    document.getElementById('sidebar').classList.toggle('open');
  });

  // ── Simulator ──
  document.getElementById('btn-start-call').addEventListener('click', () => simulator.startCall());
  document.getElementById('btn-end-call').addEventListener('click', () => simulator.endCall());
  document.getElementById('btn-sim-prewarm')?.addEventListener('click', () => simPrewarm.prewarm());
  document.getElementById('btn-sim-preview-prewarm')?.addEventListener('click', () => simPrewarm.preview());

  // Caller ID input
  document.getElementById('caller-id-input')?.addEventListener('input', e => {
    simulator.handleCallerIdInput(e.target.value);
  });

  // ── Contacts ──
  document.getElementById('btn-add-contact').addEventListener('click', () => contactModal.open());
  document.getElementById('modal-contact-close').addEventListener('click', () => contactModal.close());
  document.getElementById('modal-contact-cancel').addEventListener('click', () => contactModal.close());
  document.getElementById('modal-contact-save').addEventListener('click', () => contactModal.save());
  document.getElementById('modal-contact').addEventListener('click', e => {
    if (e.target === document.getElementById('modal-contact')) contactModal.close();
  });
  ['contact-name', 'contact-phone'].forEach(id => {
    document.getElementById(id)?.addEventListener('keydown', e => {
      if (e.key === 'Enter') contactModal.save();
    });
  });

  // ── Knowledge Base ──
  const docDropzone  = document.getElementById('doc-dropzone');
  const docFileInput = document.getElementById('doc-file-input');
  docDropzone.addEventListener('click',     () => docFileInput.click());
  docDropzone.addEventListener('dragover',  e => { e.preventDefault(); docDropzone.classList.add('drag-over'); });
  docDropzone.addEventListener('dragleave', () => docDropzone.classList.remove('drag-over'));
  docDropzone.addEventListener('drop',      e => {
    e.preventDefault();
    docDropzone.classList.remove('drag-over');
    if (e.dataTransfer.files.length) knowledge.uploadFiles([...e.dataTransfer.files]);
  });
  docFileInput.addEventListener('change', () => {
    if (docFileInput.files.length) knowledge.uploadFiles([...docFileInput.files]);
    docFileInput.value = '';
  });

  // ── Voices Library ──
  document.getElementById('btn-toggle-add-voice')?.addEventListener('click', () => voicesManager.toggleAddCard());
  document.getElementById('btn-close-add-voice')?.addEventListener('click', () => voicesManager.toggleAddCard(false));
  document.getElementById('btn-compute-voice')?.addEventListener('click', () => voicesManager.computeVoice());
  document.getElementById('btn-save-voice')?.addEventListener('click', () => voicesManager.saveVoice());

  const voiceDropzone  = document.getElementById('voice-dropzone');
  const voiceFileInput = document.getElementById('voice-file-input');
  if (voiceDropzone && voiceFileInput) {
    voiceDropzone.addEventListener('click',     () => voiceFileInput.click());
    voiceDropzone.addEventListener('dragover',  e => { e.preventDefault(); voiceDropzone.classList.add('drag-over'); });
    voiceDropzone.addEventListener('dragleave', () => voiceDropzone.classList.remove('drag-over'));
    voiceDropzone.addEventListener('drop',      e => {
      e.preventDefault();
      voiceDropzone.classList.remove('drag-over');
      if (e.dataTransfer.files[0]) voicesManager.setFile(e.dataTransfer.files[0]);
    });
    voiceFileInput.addEventListener('change', () => {
      if (voiceFileInput.files[0]) voicesManager.setFile(voiceFileInput.files[0]);
    });
  }

  // ── Simulator Fallback Text Input ──
  const simInput = document.getElementById('sim-text-input');
  const simSendBtn = document.getElementById('btn-send-sim-text');
  if (simSendBtn && simInput) {
    const doSend = () => {
      const msg = simInput.value.trim();
      if (!msg) return;
      if (!state.callActive) {
        toast.info('Click "Start Call" first to begin the call.');
        return;
      }
      simInput.value = '';
      simulator.handleUserMessage(msg);
    };
    simSendBtn.addEventListener('click', doSend);
    simInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        doSend();
      }
    });
  }

  // ── History ──
  document.getElementById('history-search')?.addEventListener('input', e => history_.filter(e.target.value));
  document.getElementById('history-filter-outcome')?.addEventListener('change', () => history_.filter());
  document.getElementById('history-filter-score')?.addEventListener('change', () => history_.filter());
  document.getElementById('btn-export-csv')?.addEventListener('click', () => history_.exportCsv());
  document.getElementById('btn-refresh-history')?.addEventListener('click', () => ui.loadHistory());

  // ── Scripts ──
  document.getElementById('btn-add-script')?.addEventListener('click', () => {
    const card = document.getElementById('add-script-card');
    if (card) {
      card.style.display = card.style.display === 'none' ? 'block' : 'none';
      if (card.style.display === 'block') {
        document.getElementById('script-title-input')?.focus();
      }
    }
  });
  document.getElementById('btn-cancel-script')?.addEventListener('click', () => {
    const card = document.getElementById('add-script-card');
    if (card) card.style.display = 'none';
    const t = document.getElementById('script-title-input');
    const c = document.getElementById('script-content-input');
    if (t) t.value = '';
    if (c) c.value = '';
  });
  document.getElementById('btn-save-script')?.addEventListener('click', async () => {
    const title = document.getElementById('script-title-input')?.value.trim();
    const content = document.getElementById('script-content-input')?.value.trim();
    if (!title || !content) {
      toast.info('Please enter both a script title and instructions.');
      return;
    }
    try {
      await api.createScript({ title, content });
      toast.success('Script saved successfully!');
      const card = document.getElementById('add-script-card');
      if (card) card.style.display = 'none';
      const t = document.getElementById('script-title-input');
      const c = document.getElementById('script-content-input');
      if (t) t.value = '';
      if (c) c.value = '';
      ui.loadScripts();
    } catch (e) {
      toast.error(`Save script failed: ${e.message}`);
    }
  });

  // ── Contact Edit Modal ──
  const closeContactEdit = () => {
    const m = document.getElementById('modal-contact-edit');
    if (m) m.style.display = 'none';
  };
  ['modal-edit-close', 'modal-edit-cancel'].forEach(id => {
    document.getElementById(id)?.addEventListener('click', closeContactEdit);
  });
  document.getElementById('modal-contact-edit')?.addEventListener('click', e => {
    if (e.target === document.getElementById('modal-contact-edit')) closeContactEdit();
  });
  document.getElementById('modal-edit-save')?.addEventListener('click', async () => {
    const id = parseInt(document.getElementById('edit-contact-id')?.value, 10);
    if (!id) return;
    const name = document.getElementById('edit-contact-name')?.value.trim();
    const phone = document.getElementById('edit-contact-phone')?.value.trim();
    if (!name || !phone) {
      toast.info('Name and phone number are required.');
      return;
    }
    const payload = {
      name,
      phone_number: phone,
      preferred_language: document.getElementById('edit-contact-language')?.value || 'en-US',
      interest_level: document.getElementById('edit-contact-interest')?.value || 'Unknown',
      last_topic: document.getElementById('edit-contact-topic')?.value.trim() || null,
      concerns: document.getElementById('edit-contact-concerns')?.value.trim() || null,
      commitments: document.getElementById('edit-contact-commitments')?.value.trim() || null,
      notes: document.getElementById('edit-contact-notes')?.value.trim() || null,
    };
    try {
      await api.updateContact(id, payload);
      toast.success('Contact memory updated successfully!');
      closeContactEdit();
      ui.loadContacts();
    } catch (e) {
      toast.error(`Update failed: ${e.message}`);
    }
  });

  // ── Call Detail Modal ──
  ['modal-detail-close', 'modal-detail-close2'].forEach(id => {
    document.getElementById(id)?.addEventListener('click', () => {
      document.getElementById('modal-call-detail').style.display = 'none';
    });
  });
  document.getElementById('modal-call-detail').addEventListener('click', e => {
    if (e.target === document.getElementById('modal-call-detail')) {
      document.getElementById('modal-call-detail').style.display = 'none';
    }
  });

  // ── Settings ──
  document.getElementById('btn-connect-backend')?.addEventListener('click', () => settings.connectBackend());
  document.getElementById('backend-url-input')?.addEventListener('keydown', e => {
    if (e.key === 'Enter') settings.connectBackend();
  });

  // ── Twilio Telephony ──
  document.getElementById('btn-save-twilio')?.addEventListener('click', () => twilioManager.saveConfig());
  document.getElementById('btn-test-twilio')?.addEventListener('click', () => twilioManager.testConnection());
  document.getElementById('btn-dial-twilio')?.addEventListener('click', () => twilioManager.dial());
  document.getElementById('btn-hangup-twilio')?.addEventListener('click', () => twilioManager.hangup());
  document.getElementById('btn-prewarm-voice')?.addEventListener('click', () => voicePrewarmManager.prewarm());
  document.getElementById('btn-preview-greeting')?.addEventListener('click', () => voicePrewarmManager.preview());
  document.getElementById('btn-quick-twilio-settings')?.addEventListener('click', () => ui.showSection('settings'));

  // ── Telephony Voice Engine Synchronization ──
  const syncTelephonyEngine = (val) => {
    twilioManager.updateEngineBadge(val);
    if (state.twilioConfig) state.twilioConfig.voice_engine = val;
    api.updateTwilioConfig({ voice_engine: val, public_base_url: api.base }).catch(() => {});
    if (val !== 'polly' && typeof voicePrewarmManager !== 'undefined') {
      voicePrewarmManager.checkStatus();
    }
    toast.info(`Telephony voice engine set to: ${val.toUpperCase()}`);
  };

  document.getElementById('phone-tts-engine')?.addEventListener('change', (e) => {
    const opt = e.target.selectedOptions ? e.target.selectedOptions[0] : null;
    const voiceId = opt ? opt.dataset.voiceId : null;
    if (voiceId) {
      voicesManager.activate(voiceId);
    } else {
      syncTelephonyEngine(e.target.value);
    }
    const phoneLang = document.getElementById('phone-call-language');
    if (phoneLang) languageEngineSync.syncFromEngine(e.target.value, phoneLang);
  });

  document.getElementById('phone-call-language')?.addEventListener('change', (e) => {
    const lang = e.target.value;
    state.selectedLanguage = lang;
    const phoneEngine = document.getElementById('phone-tts-engine');
    if (phoneEngine) languageEngineSync.syncFromLanguage(lang, phoneEngine);
    toast.info(`Dialer language set to: ${lang}`);
  });

  document.getElementById('twilio-voice-select')?.addEventListener('change', (e) => {
    syncTelephonyEngine(e.target.value);
  });

  document.getElementById('phone-contact-select')?.addEventListener('change', (e) => {
    const cid = e.target.value;
    const c = state.contacts.find(x => String(x.id) === String(cid));
    const phoneInp = document.getElementById('twilio-dial-number');
    if (c && phoneInp) {
      phoneInp.value = c.phone_number || '';
    }
  });

  // ── Simulator TTS Engine Selector ──
  document.getElementById('sim-tts-engine')?.addEventListener('change', (e) => {
    const opt = e.target.selectedOptions ? e.target.selectedOptions[0] : null;
    const voiceId = opt ? opt.dataset.voiceId : null;
    const val = e.target.value;
    const badge = document.getElementById('sim-tts-badge');
    const modelTag = document.getElementById('sim-model-tag');
    const prevBtn = document.getElementById('btn-sim-preview-prewarm');
    const chosenVoice = (voiceId && typeof voicesManager !== 'undefined')
      ? (voicesManager.voices || []).find(v => String(v.id) === String(voiceId))
      : null;

    if (badge) badge.textContent = `${val.toUpperCase()} Active`;
    if (modelTag) {
      const displayName = chosenVoice?.name?.split('(')?.[0]?.trim() || (val === 'f5tts' ? 'F5-TTS' : val === 'luxtts' ? 'LuxTTS' : val.includes('kannada') ? 'Sapna (Kannada)' : val.includes('hindi') ? 'Swara (Hindi)' : val.toUpperCase());
      modelTag.innerHTML = `<i data-lucide="cpu"></i> Groq LLaMA / ${escapeHtml(displayName)}`;
      lucide.createIcons({ nodes: [modelTag] });
    }
    if (prevBtn && chosenVoice) {
      prevBtn.dataset.voiceId = String(chosenVoice.id || '');
      if (chosenVoice.preview_url) {
        prevBtn.dataset.url = chosenVoice.preview_url;
        prevBtn.style.display = 'inline-flex';
      }
    }

    if (voiceId) {
      voicesManager.activate(voiceId);
    } else {
      toast.info(`Voice engine set to: ${val.toUpperCase()}`);
    }
    const simLang = document.getElementById('sim-language');
    if (simLang) languageEngineSync.syncFromEngine(e.target.value, simLang);
  });

  document.getElementById('btn-toggle-twilio-token')?.addEventListener('click', () => {
    const inp = document.getElementById('twilio-token-input');
    if (!inp) return;
    const isPass = inp.type === 'password';
    inp.type = isPass ? 'text' : 'password';
    const icon = document.querySelector('#btn-toggle-twilio-token i');
    if (icon) {
      icon.setAttribute('data-lucide', isPass ? 'eye-off' : 'eye');
      lucide.createIcons({ nodes: [document.getElementById('btn-toggle-twilio-token')] });
    }
  });

  document.getElementById('btn-copy-webhook')?.addEventListener('click', () => {
    const val = document.getElementById('twilio-webhook-display')?.value;
    if (!val) { toast.info('No webhook URL available.'); return; }
    navigator.clipboard.writeText(val).then(() => {
      toast.success('Inbound Webhook URL copied to clipboard!');
    }).catch(() => {
      toast.info(`Webhook: ${val}`);
    });
  });

  // Auto-fill Twilio destination phone and language on contact selection
  const syncContactPhone = (cid) => {
    const contact = state.contacts.find(c => c.id === parseInt(cid, 10));
    if (contact) {
      if (contact.phone_number) {
        const dialInp = document.getElementById('twilio-dial-number');
        if (dialInp) dialInp.value = contact.phone_number;
      }
      if (contact.preferred_language) {
        state.selectedLanguage = contact.preferred_language;
        const simLang = document.getElementById('sim-language');
        if (simLang) simLang.value = contact.preferred_language;
        const simBadge = document.getElementById('sim-lang-badge');
        if (simBadge) simBadge.textContent = contact.preferred_language;
        const phoneLang = document.getElementById('phone-call-language');
        if (phoneLang) phoneLang.value = contact.preferred_language;

        // Auto-switch voice for simulator if user is on default
        const simSel = document.getElementById('sim-tts-engine');
        if (simSel) {
          if (contact.preferred_language === 'kn-IN' && ['f5tts', 'luxtts'].includes(simSel.value)) {
            simSel.value = 'kannada_female';
          } else if (contact.preferred_language === 'hi-IN' && ['f5tts', 'luxtts'].includes(simSel.value)) {
            simSel.value = 'hindi_female';
          }
        }
      }
    }
  };
  document.getElementById('contact-select')?.addEventListener('change', e => syncContactPhone(e.target.value));
  document.getElementById('contact-select-mkt')?.addEventListener('change', e => syncContactPhone(e.target.value));

  // ── Simulator Language Selector ──
  document.getElementById('sim-language')?.addEventListener('change', (e) => {
    const lang = e.target.value;
    state.selectedLanguage = lang;
    const badge = document.getElementById('sim-lang-badge');
    if (badge) badge.textContent = lang;

    const simSel = document.getElementById('sim-tts-engine');
    if (simSel) languageEngineSync.syncFromLanguage(lang, simSel);

    // If call is live and mic is listening, update live recognition language
    if (state.recognition) {
      state.recognition.lang = lang;
    }
    toast.success(`Simulator language set to: ${lang}`);
  });

  // ── Settings Default Language ──
  document.getElementById('default-app-language')?.addEventListener('change', (e) => {
    const lang = e.target.value;
    localStorage.setItem('vocalyx_language', lang);
    state.selectedLanguage = lang;
    const simLang = document.getElementById('sim-language');
    if (simLang) simLang.value = lang;
    const simBadge = document.getElementById('sim-lang-badge');
    if (simBadge) simBadge.textContent = lang;
    const phoneLang = document.getElementById('phone-call-language');
    if (phoneLang) phoneLang.value = lang;
    toast.success(`Default assistant language updated to: ${lang}`);
  });

  // ── Message Alerts Listeners ──
  document.getElementById('btn-refresh-alerts')?.addEventListener('click', () => {
    alertsManager.loadConfig();
    toast.info('Message alert statuses refreshed.');
  });
  document.getElementById('btn-save-wa-alert')?.addEventListener('click', () => alertsManager.saveWhatsApp());
  document.getElementById('btn-test-wa-alert')?.addEventListener('click', () => alertsManager.testWhatsApp());
  document.getElementById('btn-save-sms-alert')?.addEventListener('click', () => alertsManager.saveSMS());
  document.getElementById('btn-test-sms-alert')?.addEventListener('click', () => alertsManager.testSMS());
  document.getElementById('btn-save-tg-alert')?.addEventListener('click', () => alertsManager.saveTelegram());
  document.getElementById('btn-test-tg-alert')?.addEventListener('click', () => alertsManager.testTelegram());

  document.querySelectorAll('.btn-nav-to-settings').forEach(btn => {
    btn.addEventListener('click', () => ui.showSection('settings'));
  });

  document.getElementById('btn-goto-alerts')?.addEventListener('click', () => ui.showSection('alerts'));

  document.getElementById('btn-toggle-tg-token')?.addEventListener('click', () => {
    const inp = document.getElementById('alert-tg-token');
    if (!inp) return;
    const isPass = inp.type === 'password';
    inp.type = isPass ? 'text' : 'password';
  });
}

/* ─── Boot ──────────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  lucide.createIcons();
  bindCallModeTabs();
  bindEvents();

  // Pre-load speech synthesis voices
  if ('speechSynthesis' in window) {
    window.speechSynthesis.getVoices();
    window.speechSynthesis.onvoiceschanged = () => {
      window.speechSynthesis.getVoices();
    };
  }

  // Check saved or default backend
  const targetBackend = localStorage.getItem(LS_KEY) || DEFAULT_BACKEND_URL;
  if (targetBackend) {
    api.base = targetBackend;
    checkBackendHealth(targetBackend).then(ok => {
      if (!ok) {
        toast.info('Connecting to Hugging Face backend... Check Settings if needed.');
      }
    });
  } else {
    updateStatusUI(false, 'Not connected');
  }

  // Initialize Language and Engine Sync rules
  try {
    const pEng = document.getElementById('phone-tts-engine');
    const pLang = document.getElementById('phone-call-language');
    if (pEng && pLang && typeof languageEngineSync !== 'undefined') {
      languageEngineSync.syncFromEngine(pEng.value, pLang);
    }
    const sEng = document.getElementById('sim-tts-engine');
    const sLang = document.getElementById('sim-language');
    if (sEng && sLang && typeof languageEngineSync !== 'undefined') {
      languageEngineSync.syncFromEngine(sEng.value, sLang);
    }
  } catch (syncInitErr) {
    console.warn('[Sync Init Error]', syncInitErr);
  }

  ui.showSection('dashboard');
});
