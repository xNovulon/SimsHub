// Small helpers the game-data plug-ins share (features/ea.js, refit.js, props.js, dance.js, sayit.js): asking the
// server for JSON, and saying in plain words why game data could not be read.

// GET or POST JSON. Errors carry the status and the server's own message (err.status, err.body).
export async function fetchJson(url, { body, method } = {}) {
  const opts = body === undefined ? { method: method || 'GET' }
    : { method: method || 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
  const r = await fetch(url, opts);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) {
    const err = new Error((data && data.error) || r.statusText || ('HTTP ' + r.status));
    err.status = r.status;
    err.body = data;
    throw err;
  }
  return data;
}

// Is this the server saying The Sims 4 itself could not be found (no game folder on this PC)?
export const gameMissing = e => /install not found|game_dir|Data[\\/]+Client/i.test(String((e && e.message) || e || ''));

// One sentence for an error while reading game data. what: the thing that could not be read ("the places").
export function plainError(e, what = 'this') {
  const text = String((e && e.message) || e || '');
  if (gameMissing(text)) return `The Sims 4 was not found on this PC, so ${what} can't be read from the game. Install the game (or set its folder in config.json), then try again.`;
  if (/ww_example_objects|could not be read from the game files/i.test(text)) {
    return `WickedWhims' places could not be read from the game files on this PC, so ${what} can't be listed. Check that The Sims 4 and WickedWhims are installed, then try again.`;
  }
  if (e && e.status === 404 && /unknown api/i.test(text)) return 'This needs the newest engine - close Wicked Animator and open it again.';
  return `Could not read ${what}: ${text}`;
}
