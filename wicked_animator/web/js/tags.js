// WickedWhims' animation kinds and tags (read from WickedWhims' own tag list), grouped for picking.
export const KINDS = [
  ['TEASING', 'Teasing'], ['HANDJOB', 'Handjob'], ['FOOTJOB', 'Footjob'], ['ORALJOB', 'Oral'],
  ['VAGINAL', 'Vaginal'], ['ANAL', 'Anal'], ['CLIMAX', 'Climax'],
];

export const TAG_GROUPS = [
  ['Position', ['COWGIRL', 'DOGGY', 'MISSIONARY', 'SPOONING', 'PRONEBONE', 'PILEDRIVER', 'SIXTYNINE', 'FACE_SITTING',
    'STANDING', 'SITTING', 'KNEELING', 'SIDEWAYS', 'UPSIDE_DOWN', 'CARRY', 'SPITROAST', 'FLEXIBLE']],
  ['Acts', ['BLOWJOB', 'DEEP_THROAT', 'CUNNILINGUS', 'RIMJOB', 'LICKING', 'FINGERING', 'MASTURBATION', 'TITJOB', 'THIGHJOB',
    'BUTTJOB', 'KISSING', 'GROPING', 'TITS_SUCKING', 'TOES_SUCKING', 'SPANKING', 'CHOKING', 'DOUBLE_PENETRATION', 'FISTING',
    'PEEING', 'FOREPLAY']],
  ['Finish', ['CLIMAX', 'CUMSHOT', 'CREAMPIE', 'CUM_INSIDE', 'CUM_IN_MOUTH', 'BUKKAKE', 'SQUIRT']],
  ['Mood', ['SLOW', 'PASSIONATE', 'ROUGH', 'SHY', 'AWKWARD']],
  ['Power & kink', ['FEMDOM', 'MALEDOM', 'BDSM', 'FORCED', 'FREEUSE', 'CUCK', 'ONLOOKER', 'SLEEPING', 'WEIRD', 'GROSS']],
  ['Group', ['HOMOSEXUAL', 'FUTA', 'THREESOME', 'FOURSOME', 'ORGY', 'GANGBANG', 'HAREM']],
  ['Supernatural', ['VAMPIRE', 'ALIEN', 'GHOST', 'SERVO', 'MAGIC']],
  ['Extras', ['TOY', 'DILDO', 'CAMERA', 'STORY', 'DRESSED', 'UNDER_COVERS', 'DANCE', 'CUSTOM_VOICE_SFX']],
  ['Reactions', ['INAPPROPRIATE_INDOORS', 'INAPPROPRIATE_OUTDOORS', 'LOW_REACTION', 'NO_REACTION']],
];

const SPECIAL = { SIXTYNINE: '69', PRONEBONE: 'Prone bone', FREEUSE: 'Free use', FUTA: 'Futa', SERVO: 'Servo',
  CUSTOM_VOICE_SFX: 'Custom voice/SFX', TITS_SUCKING: 'Breast sucking', BUKKAKE: 'Bukkake', ORALJOB: 'Oral' };

export function tagLabel(t) {
  return SPECIAL[t] || t.toLowerCase().replace(/_/g, ' ').replace(/^\w/, c => c.toUpperCase());
}

export const ALL_TAGS = TAG_GROUPS.flatMap(([, tags]) => tags);

// Tags that decide the WickedWhims kind: picking one of these moves the animation to that kind
// (a position that puts something in the pussy is vaginal unless it is tagged anal, and so on).
const TAG_KIND = {
  COWGIRL: 'VAGINAL', MISSIONARY: 'VAGINAL', DOGGY: 'VAGINAL', SPOONING: 'VAGINAL', PRONEBONE: 'VAGINAL', PILEDRIVER: 'VAGINAL',
  DOUBLE_PENETRATION: 'VAGINAL', CREAMPIE: 'VAGINAL',
  BLOWJOB: 'ORALJOB', DEEP_THROAT: 'ORALJOB', CUNNILINGUS: 'ORALJOB', RIMJOB: 'ORALJOB', SIXTYNINE: 'ORALJOB', FACE_SITTING: 'ORALJOB',
  LICKING: 'ORALJOB', CUM_IN_MOUTH: 'ORALJOB',
  FINGERING: 'HANDJOB', FISTING: 'HANDJOB', TITJOB: 'HANDJOB', THIGHJOB: 'HANDJOB', BUTTJOB: 'HANDJOB',
  FOREPLAY: 'TEASING', KISSING: 'TEASING', GROPING: 'TEASING', SPANKING: 'TEASING',
  CUMSHOT: 'CLIMAX', BUKKAKE: 'CLIMAX', SQUIRT: 'CLIMAX', CLIMAX: 'CLIMAX',
};
// ANAL wins over the vaginal positions (doggy + anal = anal)
export function kindForTags(tags, current) {
  const set = new Set(tags);
  if (set.has('ANAL')) return 'ANAL';
  const order = ['CLIMAX', 'ANAL', 'VAGINAL', 'ORALJOB', 'HANDJOB', 'FOOTJOB', 'TEASING'];
  const kinds = tags.map(t => TAG_KIND[t]).filter(Boolean);
  if (!kinds.length) return current;
  return order.find(k => kinds.includes(k)) || current;
}

// Which tags go with a kind, so the kind shows up in WickedWhims' tag filters too.
export const KIND_TAG = { VAGINAL: 'VAGINAL', ANAL: 'ANAL', ORALJOB: 'BLOWJOB', HANDJOB: null, FOOTJOB: null, TEASING: 'FOREPLAY', CLIMAX: 'CLIMAX' };

// Automatic undressing: what each part takes off for a kind. The giver is the male part.
export const AUTO_NAKED = {
  TEASING: { FEMALE: 'NONE', MALE: 'NONE', BOTH: 'NONE' },
  HANDJOB: { FEMALE: 'NONE', MALE: 'BOTTOM', BOTH: 'BOTTOM' },
  FOOTJOB: { FEMALE: 'NONE', MALE: 'BOTTOM', BOTH: 'BOTTOM' },
  ORALJOB: { FEMALE: 'BOTTOM', MALE: 'BOTTOM', BOTH: 'BOTTOM' },
  VAGINAL: { FEMALE: 'ALL', MALE: 'ALL', BOTH: 'ALL' },
  ANAL: { FEMALE: 'ALL', MALE: 'ALL', BOTH: 'ALL' },
  CLIMAX: { FEMALE: 'ALL', MALE: 'ALL', BOTH: 'ALL' },
};

export const NAKED_CHOICES = [['AUTO', 'Automatic'], ['NONE', 'Keep clothes on'], ['TOP', 'Top off'], ['BOTTOM', 'Bottom off'], ['ALL', 'Fully naked']];

export function nakedFor(kind, sim) {
  if (sim.naked && sim.naked !== 'AUTO') return sim.naked;
  return (AUTO_NAKED[kind] || AUTO_NAKED.VAGINAL)[sim.gender || 'BOTH'] || 'ALL';
}
