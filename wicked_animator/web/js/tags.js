// WickedWhims' animation kinds and tags (read from WickedWhims' own tag list), grouped for picking.
import { $t } from './i18n.js';
export const KINDS = [
  ['TEASING', $t('tags.teasing')], ['HANDJOB', $t('tags.handjob')], ['FOOTJOB', $t('tags.footjob')], ['ORALJOB', $t('tags.oral')],
  ['VAGINAL', $t('tags.vaginal')], ['ANAL', $t('tags.anal')], ['CLIMAX', $t('tags.climax')],
];

export const TAG_GROUPS = [
  [$t('tags.position'), ['COWGIRL', 'DOGGY', 'MISSIONARY', 'SPOONING', 'PRONEBONE', 'PILEDRIVER', 'SIXTYNINE', 'FACE_SITTING',
    'STANDING', 'SITTING', 'KNEELING', 'SIDEWAYS', 'UPSIDE_DOWN', 'CARRY', 'SPITROAST', 'FLEXIBLE']],
  [$t('tags.acts'), ['BLOWJOB', 'DEEP_THROAT', 'CUNNILINGUS', 'RIMJOB', 'LICKING', 'FINGERING', 'MASTURBATION', 'TITJOB', 'THIGHJOB',
    'BUTTJOB', 'KISSING', 'GROPING', 'TITS_SUCKING', 'TOES_SUCKING', 'SPANKING', 'CHOKING', 'DOUBLE_PENETRATION', 'FISTING',
    'PEEING', 'FOREPLAY']],
  [$t('tags.finish'), ['CLIMAX', 'CUMSHOT', 'CREAMPIE', 'CUM_INSIDE', 'CUM_IN_MOUTH', 'BUKKAKE', 'SQUIRT']],
  [$t('tags.mood'), ['SLOW', 'PASSIONATE', 'ROUGH', 'SHY', 'AWKWARD']],
  [$t('tags.power_kink'), ['FEMDOM', 'MALEDOM', 'BDSM', 'FORCED', 'FREEUSE', 'CUCK', 'ONLOOKER', 'SLEEPING', 'WEIRD', 'GROSS']],
  [$t('tags.group'), ['HOMOSEXUAL', 'FUTA', 'THREESOME', 'FOURSOME', 'ORGY', 'GANGBANG', 'HAREM']],
  [$t('tags.supernatural'), ['VAMPIRE', 'ALIEN', 'GHOST', 'SERVO', 'MAGIC']],
  [$t('tags.extras'), ['TOY', 'DILDO', 'CAMERA', 'STORY', 'DRESSED', 'UNDER_COVERS', 'DANCE', 'CUSTOM_VOICE_SFX']],
  [$t('tags.reactions'), ['INAPPROPRIATE_INDOORS', 'INAPPROPRIATE_OUTDOORS', 'LOW_REACTION', 'NO_REACTION']],
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

export const NAKED_CHOICES = [['AUTO', $t('tags.automatic')], ['NONE', $t('tags.keep_clothes_on')], ['TOP', $t('tags.top_off')], ['BOTTOM', $t('tags.bottom_off')], ['ALL', $t('tags.fully_naked')]];

export function nakedFor(kind, sim) {
  if (sim.naked && sim.naked !== 'AUTO') return sim.naked;
  return (AUTO_NAKED[kind] || AUTO_NAKED.VAGINAL)[sim.gender || 'BOTH'] || 'ALL';
}
