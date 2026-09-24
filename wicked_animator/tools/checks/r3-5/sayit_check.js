// R3-5 check: "Say it, see it" - the sentence reader (web/js/sayit.js) in Node (no browser, nothing written).
//   node tools/checks/r3-5/sayit_check.js
// The examples the window offers, spelling fixes, negations, relative follow-ups, the adults-only refusals (and that
// ordinary adult words are NOT refused), filling in what was not said with a smaller library, the plan handed to
// Magic, and the chips.
const fs = require('fs');
const path = require('path');
const H = require('../lib/harness.js');

const ROOT = path.join(__dirname, '..', '..', '..');

async function load() {
  const src = fs.readFileSync(path.join(ROOT, 'web', 'js', 'sayit.js'), 'utf8');
  return import('data:text/javascript;base64,' + Buffer.from(src).toString('base64'));
}

(async () => {
  const S = await load();
  const rows = [];
  const row = (name, ok, detail) => rows.push({ name, ok: !!ok, detail });
  const spec = t => S.resolve(S.parse(t).spec);

  // every example in the window reads to a full scene with nothing left unknown
  for (const ex of S.EXAMPLES) {
    const r = S.parse(ex);
    row(`example: "${ex.slice(0, 48)}"`, !r.refused && !r.empty && !r.unknown.length, S.chipsFor(r.spec).map(c => c.text).join(' · '));
  }
  // what the sentences say
  const a = spec("slow cowgirl on the sofa, she's teasing him, 5 seconds");
  row('cowgirl, sofa, teasing (her), slow, 5 s', a.act === 'cowgirl' && a.place === 'sofa' && a.mood === 'teasing' && a.moodBy === 'FEMALE' && a.speed <= 0.35 && a.seconds === 5, JSON.stringify(a));
  const b = spec('rough doggy on the bed, fast, he cums inside');
  row('doggy, double bed, rough, fast, finish inside', b.act === 'doggy' && b.place === 'double_bed' && b.mood === 'rough' && b.speed >= 0.8 && b.finishPart === 'inside', JSON.stringify(b));
  const c = S.parse('cowgril on the misionary bed, dogy');
  row('misspellings are fixed', c.fixes.length === 3 && c.spec.act === 'cowgirl', JSON.stringify(c.fixes));
  const d = S.parse('show me something slow');
  row('ordinary words are not "fixed" ("show" is not "slow")', !d.fixes.some(([w]) => w === 'show'), JSON.stringify(d.fixes));
  const e = spec('missionary on the bed, no kissing, not too fast');
  row('negations: no kissing, not too fast', !e.extras.kissing && e.speed < 0.8, JSON.stringify({ extras: e.extras, speed: e.speed }));
  const f = spec('two women making out, eye contact');
  row('two women, making out, eye contact', f.pair === 'ff' && f.act === 'kiss' && f.extras.eyes, JSON.stringify(f));
  const g = spec('69 on the floor');
  row('69 is a position, not a number', g.act === 'sixtynine' && g.place === 'floor', JSON.stringify({ act: g.act, place: g.place }));
  const hh = S.parse('a threesome in the shower');
  row('what it does not make is said (group, a place it has no object for)', hh.notes.some(n => /two sims/.test(n.text)) && hh.notes.some(n => /shower/.test(n.text)), hh.notes.map(n => n.text).join(' | '));
  // follow-ups on an open scene
  const base = S.parse('slow cowgirl on the sofa, 5 seconds').spec;
  const fu = (t, test, label) => { const r = S.parse(t, { current: base }); const x = S.resolve(r.spec); row(`follow-up "${t}"`, !r.fresh && test(x), label ? label(x) : S.describeChanges(base, r.spec)); };
  fu('rougher', x => x.force > S.resolve(base).force);
  fu('much faster', x => x.speed > S.resolve(base).speed + 0.3);
  fu('longer', x => x.seconds === 7.5);
  fu('2 seconds longer', x => x.seconds === 7);
  fu('add kissing', x => x.extras.kissing && x.act === 'cowgirl');
  fu('on the bed instead', x => x.place === 'double_bed' && x.act === 'cowgirl');
  fu('doggy now', x => x.act === 'doggy' && x.place === 'sofa');
  fu('finish on her back', x => x.finishPart === 'back');
  const fresh = S.parse('rough doggy on the counter, 4 seconds', { current: base });
  row('a whole new sentence starts a new scene', fresh.fresh, S.chipsFor(fresh.spec).map(x => x.text).join(' · '));
  const clampLong = S.parse('a 40 second missionary');
  row('the loop stays within 2-12 s (and says so)', clampLong.spec.seconds === S.LOOP.max && clampLong.notes.some(n => /longest/.test(n.text)), clampLong.spec.seconds);

  // adults only: refused outright, nothing parsed
  const refused = ['a teen and her boyfriend', 'she is 16 yo', 'a high school girl', 'schoolgirl cowgirl', 'l0li on the bed', 't e e n doggy',
    'little girl', 'sixteen year old', 'aged 15', 'with a dog', 'she is unconscious', 'against her will', 'barely legal missionary', 'kiddo', 'stepdaughter'];
  const notRefused = ['young adult couple on the bed', 'girl on top', 'slow cowgirl', 'two women kissing', 'she rides him hard', 'doggy style',
    'on all fours', 'passionate missionary for 12 seconds', 'her boyfriend on top', 'adult woman and man'];
  const r1 = refused.filter(t => !S.parse(t).refused);
  row(`${refused.length} sentences about minors, animals or no consent are refused`, !r1.length, r1.join(' | ') || refused.map(t => S.parse(t).refused).join(','));
  const r2 = notRefused.filter(t => S.parse(t).refused);
  row(`${notRefused.length} ordinary adult sentences are not refused`, !r2.length, r2.join(' | ') || 'none refused');
  const rr = S.parse('a teen couple');
  row('a refused sentence gives no scene at all', rr.refused === 'minors' && rr.spec === null && /Adults only/.test(rr.message), rr.message);

  // filling in with what this PC has
  const env = { acts: ['missionary', 'doggy', 'kiss'], places: [{ id: 'floor', label: 'Floor', kind: 'floor' }, { id: 'double_bed', label: 'Double bed', kind: 'bed' }] };
  const lim = S.resolve(S.parse('cowgirl on the sofa').spec, env);
  row('a position this library lacks and a missing place are swapped, with a note', env.acts.includes(lim.act) && lim.place === 'floor' && lim.actNote && lim.placeNote, `${lim.act} on ${lim.place}: ${lim.actNote} / ${lim.placeNote}`);
  const auto = S.resolve(S.parse('slow').spec, env);
  row('nothing said: a position and place are picked (marked auto)', auto.auto.act && auto.auto.place && env.acts.includes(auto.act), JSON.stringify(auto.auto));

  // the plan for Magic
  const plan = S.toMagic(S.parse("slow tender missionary on the double bed, she's close to the edge, ends in a climax, kissing, 12 seconds").spec);
  row('plan: recipe, place, a one-time finish, faces with kisses, voices', plan.recipe === 'missionary' && plan.place === 'double_bed' && plan.finish === 'inside'
    && plan.faces.FEMALE.some(([, p]) => p === 'kiss') && plan.voices && plan.voices.FEMALE && plan.tremble && plan.seconds === 12 && plan.intensity < 0.4,
  JSON.stringify({ finish: plan.finish, faces: plan.faces.FEMALE, voices: plan.voices, tremble: plan.tremble, intensity: plan.intensity }));
  const bj = S.toMagic(S.parse('blowjob, loud').spec);
  row('a busy mouth keeps its own face and voice', !bj.faces.FEMALE && bj.voices && bj.voices.FEMALE === null, JSON.stringify({ faces: bj.faces, voices: bj.voices }));
  const ff = S.toMagic(S.parse('two women, missionary, he cums on her face').spec);
  row('two women: a cum finish becomes her orgasm (no finish moment)', ff.finish === 'none' && ff.bodies.join() === 'yf,yf' && ff.resolved.finishPart === 'her', JSON.stringify({ finish: ff.finish, part: ff.resolved.finishPart }));
  const silent = S.toMagic(S.parse('silent cowgirl').spec);
  row('silent: no sounds at all', silent.sounds === false && silent.voices === 'none', JSON.stringify({ sounds: silent.sounds, voices: silent.voices }));

  // chips
  const chips = S.chipsFor(S.parse('lazy spooning in bed with kissing, 6 seconds').spec);
  const kissChip = chips.find(x => x.slot === 'extra:kissing');
  row('chips: said ones plain, picked ones marked, extras removable', chips.find(x => x.slot === 'act').text === 'Spooning' && chips.find(x => x.slot === 'force').auto && kissChip && kissChip.remove, chips.map(x => `${x.label || '+'}:${x.text}${x.auto ? '*' : ''}`).join(' '));
  const ch = S.setField(S.parse('slow cowgirl on the sofa').spec, 'place', 'loveseat');
  row('a chip change sets that field only', ch.place === 'loveseat' && ch.act === 'cowgirl' && ch.speed === 0.2, JSON.stringify({ place: ch.place, act: ch.act, speed: ch.speed }));
  row('every chip slot offers choices', ['act', 'place', 'pair', 'mood', 'speed', 'force', 'seconds', 'finish'].every(sl => S.choicesFor(sl).length > 1), '');

  const ok = H.report(rows, 'R3-5 Say it, see it (web/js/sayit.js)');
  process.exit(ok ? 0 : 1);
})().catch(e => { console.error(e); process.exit(1); });
