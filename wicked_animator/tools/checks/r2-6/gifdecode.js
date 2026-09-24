// A small GIF89a reader for the R2-6 checks: every frame composed onto the canvas (disposal 0/1 and 2), as RGBA.
//   const { width, height, frames: [{rgba, delay}], loop } = decodeGif(bytes)
function decodeGif(buf) {
  const b = buf instanceof Uint8Array ? buf : new Uint8Array(buf);
  let p = 0;
  const u8 = () => b[p++], u16 = () => { const v = b[p] | (b[p + 1] << 8); p += 2; return v; };
  const sig = String.fromCharCode(...b.slice(0, 6));
  if (sig !== 'GIF89a' && sig !== 'GIF87a') throw new Error('not a GIF');
  p = 6;
  const width = u16(), height = u16(), packed = u8();
  u8(); u8();
  let gct = null;
  if (packed & 0x80) { const n = 2 << (packed & 7); gct = b.slice(p, p + n * 3); p += n * 3; }
  const canvas = new Uint8Array(width * height * 4);
  const frames = [];
  let gce = { disposal: 0, trans: -1, delay: 0 }, loop = null;
  const subblocks = () => { const parts = []; let n; while ((n = u8())) { parts.push(b.slice(p, p + n)); p += n; } const len = parts.reduce((a, x) => a + x.length, 0); const out = new Uint8Array(len); let o = 0; for (const x of parts) { out.set(x, o); o += x.length; } return out; };
  while (p < b.length) {
    const t = u8();
    if (t === 0x3B) break;
    if (t === 0x21) {
      const label = u8();
      if (label === 0xF9) { u8(); const pk = u8(); const delay = u16(); const ti = u8(); u8(); gce = { disposal: (pk >> 2) & 7, trans: pk & 1 ? ti : -1, delay }; }
      else if (label === 0xFF) { const data = subblocks(); const id = String.fromCharCode(...data.slice(0, 11)); if (id === 'NETSCAPE2.0') loop = data[12] | (data[13] << 8); }
      else subblocks();
      continue;
    }
    if (t !== 0x2C) throw new Error('bad block 0x' + t.toString(16) + ' at ' + (p - 1));
    const x0 = u16(), y0 = u16(), w = u16(), h = u16(), ipk = u8();
    let table = gct;
    if (ipk & 0x80) { const n = 2 << (ipk & 7); table = b.slice(p, p + n * 3); p += n * 3; }
    const minCode = u8();
    const data = subblocks();
    const idx = lzwDecode(data, minCode, w * h);
    const before = gce.disposal === 3 ? canvas.slice() : null;
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
      const k = idx[y * w + x];
      if (k === gce.trans) continue;
      const o = ((y + y0) * width + x + x0) * 4;
      canvas[o] = table[k * 3]; canvas[o + 1] = table[k * 3 + 1]; canvas[o + 2] = table[k * 3 + 2]; canvas[o + 3] = 255;
    }
    frames.push({ rgba: canvas.slice(), delay: gce.delay, rect: [x0, y0, w, h] });
    if (gce.disposal === 2) for (let y = 0; y < h; y++) canvas.fill(0, ((y + y0) * width + x0) * 4, ((y + y0) * width + x0 + w) * 4);
    if (gce.disposal === 3 && before) canvas.set(before);
    gce = { disposal: 0, trans: -1, delay: 0 };
  }
  return { width, height, frames, loop };
}

function lzwDecode(data, minCode, n) {
  const clear = 1 << minCode, eoi = clear + 1;
  const out = new Uint8Array(n);
  let o = 0, size = minCode + 1, next = eoi + 1, prev = -1;
  const prefix = new Int32Array(4096), suffix = new Uint8Array(4096), len = new Int32Array(4096);
  for (let i = 0; i < clear; i++) { prefix[i] = -1; suffix[i] = i; len[i] = 1; }
  let bits = 0, cur = 0, p = 0;
  const stack = new Uint8Array(4097);
  while (o < n) {
    while (bits < size) { if (p >= data.length) return out; cur |= data[p++] << bits; bits += 8; }
    const code = cur & ((1 << size) - 1); cur >>>= size; bits -= size;
    if (code === clear) { size = minCode + 1; next = eoi + 1; prev = -1; continue; }
    if (code === eoi) break;
    let c = code, first;
    if (code >= next) {                    // the KwKwK case
      if (prev < 0) throw new Error('bad LZW');
      c = prev;
    }
    let sp = 0;
    while (c >= 0) { stack[sp++] = suffix[c]; c = prefix[c]; }
    first = stack[sp - 1];
    const extra = code >= next;
    for (let i = sp - 1; i >= 0 && o < n; i--) out[o++] = stack[i];
    if (extra && o < n) out[o++] = first;
    if (prev >= 0 && next < 4096) {
      prefix[next] = prev; suffix[next] = first; len[next] = len[prev] + 1; next++;
      if (next === (1 << size) && size < 12) size++;
    }
    prev = code;
  }
  return out;
}

module.exports = { decodeGif };
