// The app's own GIF maker (no library): one shared 255-colour palette for the whole loop (median cut), a light
// ordered dither that never flickers (the same colour on the same spot always gets the same dots), and small
// frames - every frame after the first only stores the rectangle that changed, with the unchanged pixels see-through,
// so a still background costs nothing. LZW packing as in the GIF89a spec. Loops forever.
//
//   const g = new GifMaker(480, 360, { dither: 6 });
//   g.sample(imageData)  ... for some frames      (builds the palette)
//   g.add(imageData, delayCs) ... for every frame  (after the palette is made)
//   const bytes = g.finish();                      (Uint8Array, 'image/gif')

const BAYER = [0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5];     // 4 x 4 ordered dither, 0..15
const TRANSPARENT = 255;

// A growing byte buffer.
class Bytes {
  constructor(n = 1 << 20) { this.a = new Uint8Array(n); this.n = 0; }
  room(k) { if (this.n + k > this.a.length) { const b = new Uint8Array(Math.max(this.a.length * 2, this.n + k + 1024)); b.set(this.a.subarray(0, this.n)); this.a = b; } }
  byte(v) { this.room(1); this.a[this.n++] = v & 255; }
  word(v) { this.room(2); this.a[this.n++] = v & 255; this.a[this.n++] = (v >> 8) & 255; }
  bytes(arr) { this.room(arr.length); this.a.set(arr, this.n); this.n += arr.length; }
  text(s) { for (let i = 0; i < s.length; i++) this.byte(s.charCodeAt(i)); }
  done() { return this.a.slice(0, this.n); }
}

// ---------------------------------------------------------------- palette: median cut on a 5-bit histogram
export function medianCut(hist, sums, maxColors) {
  // hist: Uint32Array(32768) counts, sums: Float64Array(32768 * 3) colour sums -> Uint8Array(n * 3)
  const bins = [];
  for (let i = 0; i < 32768; i++) if (hist[i]) bins.push(i);
  if (!bins.length) return new Uint8Array([0, 0, 0]);
  const ch = (b, c) => (c === 0 ? b >> 10 : c === 1 ? (b >> 5) & 31 : b & 31);
  const makeBox = list => {
    let n = 0, lo = [31, 31, 31], hi = [0, 0, 0];
    for (const b of list) { n += hist[b]; for (let c = 0; c < 3; c++) { const v = ch(b, c); if (v < lo[c]) lo[c] = v; if (v > hi[c]) hi[c] = v; } }
    const span = [hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]];
    const axis = span[1] >= span[0] && span[1] >= span[2] ? 1 : span[0] >= span[2] ? 0 : 2;
    return { list, n, span: span[axis], axis };
  };
  const boxes = [makeBox(bins)];
  while (boxes.length < maxColors) {
    // split the box with the most pixels times its spread (big, varied areas get more colours)
    let best = -1, score = 0;
    boxes.forEach((b, i) => { const s = b.span > 0 && b.list.length > 1 ? b.n * (b.span + 1) : 0; if (s > score) { score = s; best = i; } });
    if (best < 0) break;
    const b = boxes[best];
    b.list.sort((x, y) => ch(x, b.axis) - ch(y, b.axis));
    let acc = 0, cut = 0;
    const half = b.n / 2;
    for (; cut < b.list.length - 1; cut++) { acc += hist[b.list[cut]]; if (acc >= half) break; }
    const left = b.list.slice(0, cut + 1), right = b.list.slice(cut + 1);
    if (!right.length) { b.span = 0; continue; }
    boxes.splice(best, 1, makeBox(left), makeBox(right));
  }
  const pal = new Uint8Array(boxes.length * 3);
  boxes.forEach((b, i) => {
    let r = 0, g = 0, bl = 0, n = 0;
    for (const x of b.list) { r += sums[x * 3]; g += sums[x * 3 + 1]; bl += sums[x * 3 + 2]; n += hist[x]; }
    pal[i * 3] = Math.round(r / n); pal[i * 3 + 1] = Math.round(g / n); pal[i * 3 + 2] = Math.round(bl / n);
  });
  return pal;
}

// ---------------------------------------------------------------- LZW (GIF flavour, as in omggif's writer)
function lzw(out, index, minCode) {
  const clear = 1 << minCode, eoi = clear + 1;
  let next = eoi + 1, size = minCode + 1, cur = 0, shift = 0;
  // the code table: a generation stamp per slot, so a reset costs nothing
  const stamp = lzw.stamp || (lzw.stamp = new Uint16Array(4096 * 256));
  const codes = lzw.codes || (lzw.codes = new Uint16Array(4096 * 256));
  let gen = (lzw.gen = ((lzw.gen || 0) % 65534) + 1);
  if (gen === 1) stamp.fill(0);
  const block = new Uint8Array(255);
  let bn = 0;
  const flushBlock = () => { if (bn) { out.byte(bn); out.bytes(block.subarray(0, bn)); bn = 0; } };
  const put = b => { block[bn++] = b; if (bn === 255) flushBlock(); };
  const emit = c => { cur |= c << shift; shift += size; while (shift >= 8) { put(cur & 255); cur >>>= 8; shift -= 8; } };
  out.byte(minCode);
  emit(clear);
  let prefix = index[0];
  for (let i = 1; i < index.length; i++) {
    const k = index[i], key = (prefix << 8) | k;
    if (stamp[key] === gen) { prefix = codes[key]; continue; }
    emit(prefix);
    if (next === 4096) {
      emit(clear);
      next = eoi + 1; size = minCode + 1;
      gen = (lzw.gen = (lzw.gen % 65534) + 1);
      if (gen === 1) stamp.fill(0);
    } else {
      if (next >= (1 << size)) size++;
      stamp[key] = gen; codes[key] = next++;
    }
    prefix = k;
  }
  emit(prefix);
  emit(eoi);
  if (shift > 0) put(cur & 255);
  flushBlock();
  out.byte(0);
}

// ---------------------------------------------------------------- the maker
export class GifMaker {
  constructor(width, height, { dither = 6, maxColors = 255 } = {}) {
    this.w = width; this.h = height; this.dither = dither; this.maxColors = Math.min(255, maxColors);
    this.hist = new Uint32Array(32768); this.sums = new Float64Array(32768 * 3);
    this.palette = null; this.prev = null; this.frames = 0;
    this.out = new Bytes();
  }

  // Count the colours of a frame (every 2nd pixel) for the palette.
  sample(img, step = 2) {
    const d = img.data || img;
    for (let i = 0; i < d.length; i += 4 * step) {
      const b = ((d[i] >> 3) << 10) | ((d[i + 1] >> 3) << 5) | (d[i + 2] >> 3);
      this.hist[b]++; this.sums[b * 3] += d[i]; this.sums[b * 3 + 1] += d[i + 1]; this.sums[b * 3 + 2] += d[i + 2];
    }
  }

  _start() {
    this.palette = medianCut(this.hist, this.sums, this.maxColors);
    this.nColors = this.palette.length / 3;
    this.cache = new Int16Array(1 << 18).fill(-1);          // 6 bits per channel -> palette index
    const o = this.out;
    o.text('GIF89a');
    o.word(this.w); o.word(this.h);
    o.byte(0xF7); o.byte(0); o.byte(0);                     // a 256-entry global colour table
    const table = new Uint8Array(768);
    table.set(this.palette);
    o.bytes(table);
    o.byte(0x21); o.byte(0xFF); o.byte(11); o.text('NETSCAPE2.0'); o.byte(3); o.byte(1); o.word(0); o.byte(0);   // loop forever
  }

  _nearest(r, g, b) {
    const key = ((r >> 2) << 12) | ((g >> 2) << 6) | (b >> 2);
    let v = this.cache[key];
    if (v >= 0) return v;
    const p = this.palette, cr = (r & ~3) | 2, cg = (g & ~3) | 2, cb = (b & ~3) | 2;
    let best = 0, bd = 1e9;
    for (let i = 0; i < this.nColors; i++) {
      const dr = p[i * 3] - cr, dg = p[i * 3 + 1] - cg, db = p[i * 3 + 2] - cb;
      const dd = dr * dr * 2 + dg * dg * 4 + db * db * 3;
      if (dd < bd) { bd = dd; best = i; }
    }
    this.cache[key] = best;
    return best;
  }

  // Palette indices of a frame (with the ordered dither).
  _index(img) {
    const d = img.data || img, w = this.w, h = this.h, out = new Uint8Array(w * h), amp = this.dither / 16;
    for (let y = 0, i = 0, j = 0; y < h; y++) {
      const row = (y & 3) << 2;
      for (let x = 0; x < w; x++, i += 4, j++) {
        const t = (BAYER[row | (x & 3)] - 7.5) * amp;
        const r = d[i] + t, g = d[i + 1] + t, b = d[i + 2] + t;
        out[j] = this._nearest(r < 0 ? 0 : r > 255 ? 255 : r | 0, g < 0 ? 0 : g > 255 ? 255 : g | 0, b < 0 ? 0 : b > 255 ? 255 : b | 0);
      }
    }
    return out;
  }

  // Add a frame (ImageData or RGBA bytes of width x height), shown for delay hundredths of a second.
  add(img, delay = 5) {
    if (!this.palette) this._start();
    const idx = this._index(img), w = this.w, h = this.h, o = this.out;
    let x0 = 0, y0 = 0, x1 = w - 1, y1 = h - 1, trans = false, data = idx;
    if (this.prev) {
      // only the rectangle that changed; unchanged pixels inside it are see-through
      x0 = w; y0 = h; x1 = -1; y1 = -1;
      for (let y = 0, j = 0; y < h; y++) for (let x = 0; x < w; x++, j++) {
        if (idx[j] !== this.prev[j]) { if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y; }
      }
      if (x1 < 0) { x0 = y0 = 0; x1 = y1 = 0; }            // nothing changed: one see-through pixel
      const rw = x1 - x0 + 1, rh = y1 - y0 + 1;
      data = new Uint8Array(rw * rh);
      for (let y = 0; y < rh; y++) for (let x = 0; x < rw; x++) {
        const j = (y + y0) * w + x + x0;
        data[y * rw + x] = idx[j] === this.prev[j] ? TRANSPARENT : idx[j];
      }
      trans = true;
    }
    // graphic control: keep the frame under the next one (disposal 1), delay, see-through index
    o.byte(0x21); o.byte(0xF9); o.byte(4); o.byte((1 << 2) | (trans ? 1 : 0)); o.word(Math.max(2, Math.round(delay))); o.byte(TRANSPARENT); o.byte(0);
    o.byte(0x2C); o.word(x0); o.word(y0); o.word(x1 - x0 + 1); o.word(y1 - y0 + 1); o.byte(0);
    lzw(o, data, 8);
    this.prev = idx;
    this.frames++;
  }

  get size() { return this.out.n; }

  finish() {
    if (!this.palette) this._start();
    this.out.byte(0x3B);
    return this.out.done();
  }
}

// Make a GIF from frames (ImageData[]), each shown for delay hundredths of a second.
export function makeGif(frames, { width, height, delay = 5, dither = 6 } = {}) {
  const g = new GifMaker(width || frames[0].width, height || frames[0].height, { dither });
  const step = Math.max(1, Math.floor(frames.length / 24));
  for (let i = 0; i < frames.length; i += step) g.sample(frames[i]);
  for (const f of frames) g.add(f, delay);
  return g.finish();
}
