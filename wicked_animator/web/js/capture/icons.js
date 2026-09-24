// The icons capture uses (added to the app's icon sheet once) and its stylesheet (linked when index.html has not).
const ICONS = {
  'cap-video': '<rect x="3" y="6" width="13" height="12" rx="2.5" stroke="currentColor" stroke-width="1.7" fill="none"/><path d="m16 10.5 5-3v9l-5-3z" stroke="currentColor" stroke-width="1.7" fill="none" stroke-linejoin="round"/>',
  'cap-webcam': '<circle cx="12" cy="10" r="6.5" stroke="currentColor" stroke-width="1.7" fill="none"/><circle cx="12" cy="10" r="2.4" stroke="currentColor" stroke-width="1.7" fill="none"/><path d="M8 20h8M12 16.5V20" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>',
  'cap-photo': '<rect x="3" y="5" width="18" height="14" rx="2.5" stroke="currentColor" stroke-width="1.7" fill="none"/><circle cx="9" cy="10" r="1.8" fill="currentColor"/><path d="m4.5 17 5-4.5 3.5 3 2.5-2 4 3.5" stroke="currentColor" stroke-width="1.6" fill="none" stroke-linejoin="round"/>',
  'cap-face': '<path d="M4 8V5.5A1.5 1.5 0 0 1 5.5 4H8M16 4h2.5A1.5 1.5 0 0 1 20 5.5V8M20 16v2.5a1.5 1.5 0 0 1-1.5 1.5H16M8 20H5.5A1.5 1.5 0 0 1 4 18.5V16" stroke="currentColor" stroke-width="1.7" fill="none" stroke-linecap="round"/><circle cx="9.5" cy="10.5" r="1" fill="currentColor"/><circle cx="14.5" cy="10.5" r="1" fill="currentColor"/><path d="M9.3 14.3c1.5 1.4 3.9 1.4 5.4 0" stroke="currentColor" stroke-width="1.6" fill="none" stroke-linecap="round"/>',
  'cap-film': '<rect x="3" y="4" width="18" height="16" rx="2.5" stroke="currentColor" stroke-width="1.7" fill="none"/><path d="M7 4v16M17 4v16M3 9h4M3 15h4M17 9h4M17 15h4" stroke="currentColor" stroke-width="1.5"/><path d="m10.5 9.5 4 2.5-4 2.5z" fill="currentColor"/>',
  'cap-shield': '<path d="M12 3 19 6v5.5c0 4.3-2.9 8-7 9.5-4.1-1.5-7-5.2-7-9.5V6z" stroke="currentColor" stroke-width="1.7" fill="none" stroke-linejoin="round"/><path d="m9 12 2 2 4-4" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
  'cap-download': '<path d="M12 4v11m0 0-4.5-4.5M12 15l4.5-4.5M5 19.5h14" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
};
export function ensureIcons() {
  const sheet = document.querySelector('svg[aria-hidden="true"]') || document.querySelector('body > svg');
  for (const [id, inner] of Object.entries(ICONS)) {
    if (document.getElementById('i-' + id)) continue;
    let host = sheet;
    if (!host) { host = document.createElementNS('http://www.w3.org/2000/svg', 'svg'); host.setAttribute('aria-hidden', 'true'); host.style.display = 'none'; document.body.append(host); }
    const sym = document.createElementNS('http://www.w3.org/2000/svg', 'symbol');
    sym.id = 'i-' + id; sym.setAttribute('viewBox', '0 0 24 24'); sym.innerHTML = inner;
    host.append(sym);
  }
}
export function ensureStyles() {
  if (document.querySelector('link[href$="css/capture.css"]')) return;
  const l = document.createElement('link');
  l.rel = 'stylesheet'; l.href = 'css/capture.css';
  document.head.append(l);
}

