// Talking to the local server.
// Errors carry the HTTP status (err.status) and the server's answer (err.body), so callers can tell
// "this server doesn't have that feature" (404) or "that name is taken" (409) apart from a real failure.
async function j(url, opts) {
  const r = await fetch(url, opts);
  const body = await r.json().catch(() => ({}));
  if (!r.ok) {
    const err = new Error(body.error || r.statusText || ('HTTP ' + r.status));
    err.status = r.status;
    err.body = body;
    throw err;
  }
  return body;
}
const post = (url, data) => j(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });

// The file name the server keeps a project under - exactly the rule of backend/projects.py safe(), so a clash
// with another saved animation is seen before saving. Letters and digits of every alphabet stay (an Arabic name
// stays Arabic), and so do the punctuation marks Windows allows ( ) . , ' ! & + - _. Python's \w keeps letters,
// digits and _ but no accent marks that are separate characters, so \p{M} is left out on purpose. Spaces are
// squeezed to one, dots and spaces come off both ends, 80 characters at most, and Windows' reserved device names
// (CON, NUL, COM1...) get a '_'. Compare the result lower-case: Windows file names ignore case.
const RESERVED = /^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])$/i;
const trimDotsSpaces = s => s.replace(/^[ .]+|[ .]+$/g, '');
export function projectFileName(name) {
  let s = String(name || '').replace(/[^\p{L}\p{N}_ \-().,'!&+]+/gu, '');
  s = trimDotsSpaces(s.split(' ').filter(Boolean).join(' '));
  s = trimDotsSpaces(Array.from(s).slice(0, 80).join(''));      // 80 characters, not 80 UTF-16 halves
  if (RESERVED.test(s)) s += '_';
  return s || 'untitled';
}

// Automated test browsers keep their crash-recovery copy apart from yours, so a test can never replace or clear
// your unfinished work.
export const RECOVERY_SLOT = typeof navigator !== 'undefined' && navigator.webdriver ? '?slot=test' : '';

export const api = {
  status: () => j('/api/status'),
  rig: key => j(`/api/rig?key=${key}`),
  body: frame => j(`/api/body?frame=${frame}`),
  // tone: a skin tone, or 'tone~tray:index' for a Tray sim's skin with its own look (makeup, brows, tattoos...)
  skinUrl: (frame, tone = '') => {
    const [t, look] = String(tone || '').split('~');
    const [tray, index] = (look || '').split(':');
    return `/api/skin?frame=${frame}${t ? '&tone=' + t : ''}${tray ? `&tray=${encodeURIComponent(tray)}&index=${+index || 0}` : ''}`;
  },
  tones: () => j('/api/tones'),
  furniture: () => j('/api/furniture'),
  library: (q = {}) => j('/api/library?' + new URLSearchParams(q)),
  animation: (id, step = 1) => j(`/api/animation?id=${id}&step=${step}`),
  poses: () => j('/api/poses'),
  projects: () => j('/api/projects'),
  project: name => j('/api/project?name=' + encodeURIComponent(name)),
  projectByUid: uid => j('/api/project?uid=' + encodeURIComponent(uid)),
  thumbUrl: file => '/api/project_thumb?name=' + encodeURIComponent(file),
  // -> { saved, file, uid, renamed }: the server never writes over a different animation; when the name is taken
  // it keeps both and saves this one as "Name (2)" (renamed: true)
  saveProject: p => post('/api/project', p),
  removeProject: file => post('/api/project_remove', { file }),
  // "My poses" live on the server (saves\FitStudio\animator_my_poses.json), so clearing the browser never loses them
  myPoses: () => j('/api/my_poses'),
  saveMyPoses: list => post('/api/my_poses', list),
  progressions: () => j('/api/progressions'),
  saveProgressions: list => post('/api/progressions', list),
  export: p => post('/api/export', p),
  bundle: req => post('/api/bundle', req),
  reveal: path => post('/api/reveal', { path }),
  exports: () => j('/api/exports'),
  sounds: () => j('/api/sounds'),
  recovery: () => j('/api/recovery' + RECOVERY_SLOT),
  saveRecovery: data => post('/api/recovery' + RECOVERY_SLOT, data),
  clearRecovery: () => post('/api/recovery_clear' + RECOVERY_SLOT, {}),
  // reference pictures / videos (spec_editing 12): kept next to the saved animations, per animation id
  uploadRef: (uid, file) => fetch(`/api/reference?uid=${encodeURIComponent(uid)}&name=${encodeURIComponent(file.name || 'reference')}`,
    { method: 'POST', headers: { 'Content-Type': file.type || 'application/octet-stream' }, body: file })
    .then(async r => { const b = await r.json().catch(() => ({})); if (!r.ok) throw Object.assign(new Error(b.error || r.statusText || ('HTTP ' + r.status)), { status: r.status, body: b }); return b; }),
  refUrl: (uid, file) => `/api/reference_file?uid=${encodeURIComponent(uid)}&file=${encodeURIComponent(file)}`,
  tray: () => j('/api/tray'),
  trayThumb: simId => '/api/tray_thumb?sim=' + encodeURIComponent(simId),
  traySim: (tray, index) => j(`/api/tray_sim?tray=${encodeURIComponent(tray)}&index=${index}`),
};
