// Finds English text that is still written into the app instead of coming from the catalogs (web/i18n/*.json).
//   node tools/checks/i18n/scan_strings.js [--list] [--json]
// Scans web/js/**/*.js and web/index.html:
//   - JS: string literals and template text that read like English words for people (two or more words, or one
//     capitalised word where the app shows text: title/label/text..., toast(), h(tag, attrs, 'text'), .textContent =).
//     Skipped: $t('key') and its keys, imports, console.*, comparisons, CSS selectors, class names, markup, shaders.
//   - index.html: text and title/placeholder/aria-label/alt attributes of elements without a data-i18n* attribute.
// Everything reported must be moved into the catalogs or listed, with its reason, in allowlist.txt next to this file
// ("<file>|<exact text>" - the file relative to web/, * for any file). Exit code 1 when anything is left.
const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..', '..', '..');
const WEB = path.join(ROOT, 'web');
const argv = process.argv.slice(2);

// ---------------------------------------------------------------- allowlist
function loadAllow() {
  const file = path.join(__dirname, 'allowlist.txt');
  const out = [];
  if (!fs.existsSync(file)) return out;
  for (const raw of fs.readFileSync(file, 'utf8').split('\n')) {
    const line = raw.replace(/\s+$/, '');
    if (!line || line.startsWith('#')) continue;
    const i = line.indexOf('|');
    if (i < 0) continue;
    out.push({ file: line.slice(0, i).trim(), text: line.slice(i + 1), used: 0 });
  }
  return out;
}

// ---------------------------------------------------------------- a small JavaScript lexer
// -> [{type: 'str'|'tpl'|'punct'|'word'|'num'|'regex', value, line, raw}] (comments dropped). Template literals come as
// one 'tpl' token with .parts (the text between ${}) and their expressions are lexed recursively into .inner.
function lex(src) {
  const toks = [];
  let i = 0, line = 1;
  const n = src.length;
  const prevSignificant = () => { for (let k = toks.length - 1; k >= 0; k--) return toks[k]; return null; };
  const regexAllowed = () => {
    const p = prevSignificant();
    if (!p) return true;
    if (p.type === 'num' || p.type === 'str' || p.type === 'tpl' || p.type === 'regex') return false;
    if (p.type === 'word') return /^(return|typeof|case|do|else|in|of|new|delete|void|throw|instanceof|yield|await)$/.test(p.value);
    return !/^[)\]}]$/.test(p.value);
  };
  function readTemplate() {       // at the opening backtick
    const start = line;
    i++;
    const parts = [], inner = [];
    let text = '';
    while (i < n) {
      const c = src[i];
      if (c === '\\') { text += src.slice(i, i + 2); if (src[i + 1] === '\n') line++; i += 2; continue; }
      if (c === '`') { i++; break; }
      if (c === '$' && src[i + 1] === '{') {
        parts.push(text); text = '';
        i += 2;
        let depth = 1;
        const exprStart = i;
        // find the matching }, skipping strings, templates and comments inside
        while (i < n && depth) {
          const d = src[i];
          if (d === '`') { skipTemplate(); continue; }
          if (d === '"' || d === "'") { skipString(d); continue; }
          if (d === '/' && src[i + 1] === '/') { while (i < n && src[i] !== '\n') i++; continue; }
          if (d === '/' && src[i + 1] === '*') { const e = src.indexOf('*/', i + 2); i = e < 0 ? n : e + 2; continue; }
          if (d === '\n') line++;
          if (d === '{') depth++;
          else if (d === '}') depth--;
          i++;
        }
        inner.push(...lex(src.slice(exprStart, i - 1)).map(t => ({ ...t, line: t.line + start - 1 })));
        continue;
      }
      if (c === '\n') line++;
      text += c;
      i++;
    }
    parts.push(text);
    return { type: 'tpl', parts, inner, line: start };
  }
  function skipTemplate() {
    i++;
    while (i < n) {
      const c = src[i];
      if (c === '\\') { i += 2; continue; }
      if (c === '`') { i++; return; }
      if (c === '$' && src[i + 1] === '{') {
        i += 2; let depth = 1;
        while (i < n && depth) { const d = src[i]; if (d === '`') { skipTemplate(); continue; } if (d === '"' || d === "'") { skipString(d); continue; } if (d === '{') depth++; else if (d === '}') depth--; if (d === '\n') line++; i++; }
        continue;
      }
      if (c === '\n') line++;
      i++;
    }
  }
  function skipString(q) { i++; while (i < n && src[i] !== q) { if (src[i] === '\\') i++; else if (src[i] === '\n') break; i++; } i++; }
  while (i < n) {
    const c = src[i];
    if (c === '\n') { line++; i++; continue; }
    if (/\s/.test(c)) { i++; continue; }
    if (c === '/' && src[i + 1] === '/') { while (i < n && src[i] !== '\n') i++; continue; }
    if (c === '/' && src[i + 1] === '*') { const e = src.indexOf('*/', i + 2); const body = src.slice(i, e < 0 ? n : e); line += (body.match(/\n/g) || []).length; i = e < 0 ? n : e + 2; continue; }
    if (c === '"' || c === "'") {
      const s = i; let v = ''; i++;
      while (i < n && src[i] !== c) { if (src[i] === '\\') { const e = src[i + 1]; v += e === 'n' ? '\n' : e === 't' ? '\t' : e === 'u' ? String.fromCharCode(parseInt(src.slice(i + 2, i + 6), 16)) : e; i += e === 'u' ? 6 : 2; continue; } v += src[i]; i++; }
      i++;
      toks.push({ type: 'str', value: v, line, raw: src.slice(s, i) });
      continue;
    }
    if (c === '`') { toks.push(readTemplate()); continue; }
    if (c === '/' && regexAllowed()) {
      const s = i; i++;
      let cls = false;
      while (i < n) { const d = src[i]; if (d === '\\') { i += 2; continue; } if (d === '[') cls = true; else if (d === ']') cls = false; else if (d === '/' && !cls) break; else if (d === '\n') break; i++; }
      i++;
      while (i < n && /[a-z]/i.test(src[i])) i++;
      toks.push({ type: 'regex', value: src.slice(s, i), line });
      continue;
    }
    if (/[A-Za-z_$]/.test(c)) { const s = i; while (i < n && /[\w$]/.test(src[i])) i++; toks.push({ type: 'word', value: src.slice(s, i), line }); continue; }
    if (/[0-9]/.test(c)) { const s = i; while (i < n && /[\w.]/.test(src[i])) i++; toks.push({ type: 'num', value: src.slice(s, i), line }); continue; }
    const three = src.slice(i, i + 3), two = src.slice(i, i + 2);
    if (['===', '!==', '...', '**=', '>>>', '??='].includes(three)) { toks.push({ type: 'punct', value: three, line }); i += 3; continue; }
    if (['==', '!=', '=>', '&&', '||', '??', '?.', '<=', '>=', '++', '--', '+=', '-=', '*=', '/='].includes(two)) { toks.push({ type: 'punct', value: two, line }); i += 2; continue; }
    toks.push({ type: 'punct', value: c, line }); i++;
  }
  return toks;
}

// ---------------------------------------------------------------- what counts as text for people
const SMALL = /\b(the|a|an|to|and|of|in|on|is|it|its|for|with|this|that|you|your|no|not|or|at|by|from|as|are|was|be|can|will|has|have|here|there|one|all|any|more|first|then|when|what|how|than|into|them|they|their|him|her|his|she|he|each|every|only|also|now|yet|too|off|out|up|down|back|again)\b/i;
// template text that is CSS, markup or a class list, not words for people
const CSSISH = /(px|em|rem|deg|ms|vh|vw|%)\b|[;{}<>=]|^\s*(btn|icon-btn|seg|chip|pill|card|row|is|has|on|off|active|hidden|small|ghost|primary|soft|danger|muted|sm)\b|\b(translate|rotate|scale|rgba?|hsla?|calc|var|url|inset|solid|dashed|repeat|linear|ease|cubic|bold|italic|normal|monospace|sans)\b/;
const UI_PROP = /^(label|title|sub|desc|hint|text|heading|placeholder|tip|note|short|help|msg|message|caption|alt|okLabel|empty|detail|blurb|line|status|warn|error|reason|subtitle|lead|intro|summary)$/;
function prose(s, strong) {
  const t = s.trim();
  if (!/[A-Za-z]{2}/.test(t)) return false;
  if (/^<(path|circle|rect|svg|g|line|polyline|polygon|ellipse|defs|symbol|use|stop)\b/.test(t)) return false;
  if (/\b(uniform|varying|gl_Position|void main|vec[234]|sampler2D)\b/.test(t)) return false;
  if (/,\s*(sans-serif|monospace|serif)\b/.test(t)) return false;
  if (/^[\w.-]+\.(js|css|json|png|svg|webm|wav|ogg|package|txt|bvh|fbx|gif|jpg|zip|ww|xml)$/i.test(t)) return false;
  if (/^(https?:|\/|\.\/|\.\.\/|#|data:|blob:|[a-z]+\/[\w.+-]+$)/.test(t)) return false;
  if (/^[a-z0-9_$.:\-/#?&=%*@\[\]()>+~,"' ]+$/.test(t) && !(/ /.test(t) && SMALL.test(t) && !/[-_]\w/.test(t))) return false; // selectors, ids, class lists
  if (/b__|__/.test(t)) return false;
  const words = t.match(/[A-Za-z][A-Za-z']+/g) || [];
  if (words.length >= 2 && /\s/.test(t)) return /^[A-Z]/.test(t) || SMALL.test(t) || /[.!?:]$/.test(t);
  return strong && /^[A-Z][a-z]{2,}[a-z.…!?]*$/.test(t);
}

function scanJs(rel, src, allow) {
  const out = [];
  const toks = lex(src);
  const visit = (list) => {
    for (let k = 0; k < list.length; k++) {
      const tk = list[k];
      if (tk.type === 'tpl') visit(tk.inner);
      if (tk.type !== 'str' && tk.type !== 'tpl') continue;
      const prev = list[k - 1] || {}, prev2 = list[k - 2] || {}, next = list[k + 1] || {};
      const text = tk.type === 'str' ? tk.value : tk.parts.join('{}');
      // skipped places
      if (prev.value === '(' && (prev2.value === '$t' || prev2.value === 't')) continue;               // $t('key')
      if (prev.value === 'from' || prev2.value === 'import' || prev.value === 'import') continue;
      if (next.value === ':' && (prev.value === '{' || prev.value === ',')) continue;                  // an object key
      if (['===', '!==', '==', '!='].includes(prev.value) || ['===', '!==', '==', '!='].includes(next.value)) continue;
      if (prev.value === 'case') continue;
      if (prev.value === ':' && /^(words|keys|id|class|icon|type|kind|group_id|style|href|src|role)$/.test(prev2.value || '')) continue;   // search words, ids
      if (prev.value === '[' && list[k - 2] && (list[k - 2].type === 'word' || list[k - 2].value === ']' || list[k - 2].value === ')')) continue; // obj['key']
      // the call it is an argument of (the nearest open paren)
      let depth = 0, callee = '';
      for (let j = k - 1; j >= 0 && j > k - 400; j--) {
        const v = list[j].value;
        if (v === ')' || v === ']' || v === '}') depth++;
        else if (v === '(' || v === '[' || v === '{') { if (depth === 0) { if (v === '(') callee = [list[j - 3], list[j - 2], list[j - 1]].filter(Boolean).map(x => x.value).join(''); break; } depth--; }
      }
      if (/(console\.\w+|querySelector(All)?|getElementById|closest|matches|addEventListener|removeEventListener|getAttribute|setAttribute|toggleAttribute|hasAttribute|createElement(NS)?|getItem|setItem|removeItem|localStorage\w*|dispatchEvent|getContext|setProperty|RegExp|fetch|fetchJson|api\.\w+|getJson|postJson|import|require|\$t|\bt)$/.test(callee)) continue;
      const strongCtx = (prev.value === ':' && UI_PROP.test(prev2.value || '')) || /(toast|h|section|tip|confirmBox|choiceBox|modal|choiceBar|toggleRow)$/.test(callee) && prev.value !== '(' ||
        /^(toast|section|tip|choiceBar)$/.test(prev2.value || '') && prev.value === '(' ||
        (prev.value === '=' && /^(textContent|innerText|title|placeholder|label|innerHTML)$/.test(prev2.value || ''));
      const parts = tk.type === 'str' ? [tk.value] : tk.parts;
      const hit = parts.some(p => prose(p, strongCtx)) || (tk.type === 'tpl' && tk.parts.some(p => /(^|\s)[A-Za-z]{3,}('s)?([\s.,:;!?)]|$)/.test(p) && /\s/.test(p) && !/^[\s\w-]*$/.test(p.replace(/[A-Za-z]{3,}/g, '')) === false && !CSSISH.test(p)));
      if (!hit) continue;
      if (/^<[a-z]/i.test(text.trim()) && /<\/?(b|kbd|i|em|strong|span|br|small|code)\b/.test(text) === false && tk.type === 'str') continue;
      const a = allow.find(x => (x.file === '*' || x.file === rel) && (x.text === text || x.text === text.trim()));
      if (a) { a.used++; continue; }
      out.push({ file: rel, line: tk.line, text });
    }
  };
  visit(toks);
  return out;
}

// ---------------------------------------------------------------- index.html
function scanHtml(rel, src, allow) {
  const out = [];
  const body = src.replace(/<script[\s\S]*?<\/script>/gi, m => m.replace(/[^\n]/g, ' '))
    .replace(/<style[\s\S]*?<\/style>/gi, m => m.replace(/[^\n]/g, ' '))
    .replace(/<svg[\s\S]*?<\/svg>/gi, m => m.replace(/[^\n]/g, ' '))
    .replace(/<!--[\s\S]*?-->/g, m => m.replace(/[^\n]/g, ' '));
  const stack = [];          // {tag, i18n}
  const rx = /<(\/?)([a-zA-Z][\w-]*)([^>]*)>|([^<]+)/g;
  const VOID = /^(meta|link|img|input|br|hr|source|use|path|stop)$/i;
  let m;
  const lineAt = idx => body.slice(0, idx).split('\n').length;
  while ((m = rx.exec(body))) {
    if (m[4] !== undefined) {
      const text = m[4].replace(/&[a-z]+;|&#\d+;/g, ' ').trim();
      if (!/[A-Za-z]{2}/.test(text) || /^(title|head)$/i.test((stack[stack.length - 1] || {}).tag || '')) continue;
      if (stack.some(s => s.i18n)) continue;
      const a = allow.find(x => (x.file === '*' || x.file === rel) && x.text === text);
      if (a) { a.used++; continue; }
      out.push({ file: rel, line: lineAt(m.index), text });
      continue;
    }
    const [, close, tag, attrs] = m;
    if (close) { while (stack.length && stack.pop().tag.toLowerCase() !== tag.toLowerCase()); continue; }
    for (const at of ['title', 'placeholder', 'aria-label', 'alt']) {
      const v = new RegExp(`\\s${at}="([^"]*)"`).exec(attrs);
      if (v && /[A-Za-z]{2}/.test(v[1]) && !new RegExp(`data-i18n-${at}=`).test(attrs)) {
        const a = allow.find(x => (x.file === '*' || x.file === rel) && x.text === v[1]);
        if (a) a.used++; else out.push({ file: rel, line: lineAt(m.index), text: `${at}="${v[1]}"` });
      }
    }
    if (!VOID.test(tag) && !/\/$/.test(attrs)) stack.push({ tag, i18n: /\sdata-i18n(-html)?=/.test(attrs) });
  }
  return out;
}

// ---------------------------------------------------------------- run
function scanAll() {
  const allow = loadAllow();
  const found = [];
  const files = [];
  (function walk(d) { for (const f of fs.readdirSync(d).sort()) { const p = path.join(d, f); if (fs.statSync(p).isDirectory()) walk(p); else if (f.endsWith('.js')) files.push(p); } })(path.join(WEB, 'js'));
  for (const f of files) {
    const rel = path.relative(WEB, f).split(path.sep).join('/');
    found.push(...scanJs(rel, fs.readFileSync(f, 'utf8'), allow));
  }
  found.push(...scanHtml('index.html', fs.readFileSync(path.join(WEB, 'index.html'), 'utf8'), allow));
  return { found, allow };
}

if (require.main === module) {
  const { found, allow } = scanAll();
  const stale = allow.filter(a => !a.used);
  if (argv.includes('--json')) { console.log(JSON.stringify({ found, stale }, null, 1)); process.exit(found.length ? 1 : 0); }
  const byFile = {};
  for (const f of found) (byFile[f.file] = byFile[f.file] || []).push(f);
  if (argv.includes('--list') || found.length) {
    for (const [file, list] of Object.entries(byFile)) {
      console.log(`${file} (${list.length})`);
      for (const f of list) console.log(`  ${String(f.line).padStart(5)}  ${JSON.stringify(f.text).slice(0, 150)}`);
    }
  }
  if (stale.length) console.log(`\n${stale.length} allowlist line(s) match nothing any more:\n` + stale.map(a => `  ${a.file}|${a.text}`).join('\n'));
  console.log(`\n${found.length ? 'FAIL' : 'PASS'}  ${found.length} English text(s) outside the catalogs; ${allow.length - stale.length} allowlisted`);
  process.exit(found.length ? 1 : 0);
}

module.exports = { lex, prose, scanJs, scanHtml, scanAll };
