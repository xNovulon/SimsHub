// "Say it, see it" (build plan R3-5, needs.md W5): one typed sentence becomes a finished Magic scene.
//   "slow cowgirl on the sofa, she's teasing him, 5 seconds"
//     -> Position Cowgirl · Place Sofa · Mood Teasing (her) · Speed Slow · Loop 5 s
// An offline word parser - no AI model, nothing downloaded, nothing leaves the PC:
//   - a vocabulary of positions, places, who is in it, moods, speeds, strengths, lengths, finishes and extras
//     (kissing, eye contact, trembling, loud or quiet...), matched longest phrase first;
//   - misspellings are fixed by edit distance ("cowgril", "misionary", "dogy style", "cunilingus"), while ordinary
//     English words are left alone;
//   - "no kissing", "not too fast" (negations), "much rougher", "a bit slower", "2 seconds longer" (relative);
//   - follow-ups change the scene that is open: "rougher", "longer", "add kissing", "on the bed instead", "doggy now".
// Adults only: a sentence with any word about minors (or animals, or no consent) is refused outright - nothing is
// parsed, shown or made from it.
// Pure: no DOM and no three.js, so node checks import it directly (tools/checks/r3-5).

// ---------------------------------------------------------------- what can be made
// pen: penetration (a strap-on for two women); mouth: whose mouth is busy (their face stays the act's own);
// kiss: their faces are close enough to kiss; finish: where a plain "climax" goes for this act.
export const ACTS = {
  cowgirl: { label: 'Cowgirl', place: 'double_bed', pen: true, kiss: true, finish: 'inside' },
  missionary: { label: 'Missionary', place: 'double_bed', pen: true, kiss: true, finish: 'inside' },
  doggy: { label: 'Doggy', place: 'double_bed', pen: true, finish: 'inside' },
  standing: { label: 'Standing', place: 'floor', pen: true, kiss: true, finish: 'inside' },
  spooning: { label: 'Spooning', place: 'double_bed', pen: true, kiss: true, finish: 'inside' },
  pronebone: { label: 'Prone bone', place: 'double_bed', pen: true, finish: 'inside' },
  sitting: { label: 'Lap ride', place: 'sofa', pen: true, kiss: true, finish: 'inside' },
  anal: { label: 'Anal', place: 'double_bed', pen: true, finish: 'inside' },
  carry: { label: 'Carry', place: 'floor', pen: true, kiss: true, finish: 'inside' },
  bj: { label: 'Blowjob', place: 'floor', mouth: 'FEMALE', finish: 'face' },
  handjob: { label: 'Handjob', place: 'double_bed', finish: 'belly' },
  titjob: { label: 'Titjob', place: 'double_bed', finish: 'chest' },
  cunni: { label: 'Cunnilingus', place: 'double_bed', mouth: 'MALE', finish: 'her' },
  fingering: { label: 'Fingering', place: 'double_bed', kiss: true, finish: 'her' },
  sixtynine: { label: '69', place: 'double_bed', mouth: 'BOTH', finish: 'face' },
  kiss: { label: 'Making out', place: 'floor', kiss: true, finish: 'her' },
};
export const PLACES = {
  floor: 'Floor', double_bed: 'Double bed', single_bed: 'Single bed', sofa: 'Sofa', loveseat: 'Loveseat',
  chair_living: 'Armchair', counter: 'Counter', table_dining: 'Table', wall: 'Wall',
};
export const PAIRS = {
  couple: { label: 'Woman & man', bodies: ['yf', 'ym'] },
  ff: { label: 'Two women', bodies: ['yf', 'yf'] },
  mm: { label: 'Two men', bodies: ['ym', 'ym'] },
  futa: { label: 'Woman & futa', bodies: ['yf', 'yf_futa'] },
};
// speed (how fast) and force (how hard) 0..1; faces: [receiver, giver] over the loop (FACE_PRESETS ids); the one who
// teases gets the teasing faces; voice: [set, every s] for the receiver and the giver.
export const MOODS = {
  tender: { label: 'Tender', speed: 0.25, force: 0.2, faces: [['relaxed', 'pleasure', 'moan'], ['relaxed', 'pleasure']], voice: [['moan_soft', 4], ['breath', 5]] },
  passionate: { label: 'Passionate', speed: 0.6, force: 0.65, faces: [['pleasure', 'moan', 'ecstasy'], ['pleasure', 'intense']], voice: [['moan', 2.4], ['woohoo', 3.2]] },
  rough: { label: 'Rough', speed: 0.85, force: 0.95, faces: [['moan', 'ecstasy', 'moan'], ['intense', 'pleasure']], voice: [['moan', 1.8], ['woohoo', 2.4]] },
  teasing: { label: 'Teasing', speed: 0.3, force: 0.3, faces: [['seductive', 'bite', 'seductive'], ['pleasure', 'moan']], voice: [['moan_soft', 4], ['breath', 4.5]], teaser: true },
  playful: { label: 'Playful', speed: 0.5, force: 0.45, faces: [['smile', 'bite', 'pleasure'], ['smile', 'pleasure']], voice: [['moan_soft', 3], ['breath', 4]] },
  lazy: { label: 'Lazy', speed: 0.18, force: 0.2, faces: [['sleepy', 'relaxed', 'pleasure'], ['relaxed', 'sleepy']], voice: [['moan_soft', 5], ['breath', 6]] },
  shy: { label: 'Shy', speed: 0.3, force: 0.25, faces: [['bite', 'relaxed', 'pleasure'], ['smile', 'pleasure']], voice: [['moan_soft', 5], ['breath', 6]] },
};
export const FINISHES = { none: 'No finish', inside: 'Inside', face: 'Face', chest: 'Chest', belly: 'Belly', back: 'Back', butt: 'Butt', feet: 'Feet', her: 'Her orgasm' };
export const EXTRAS = {
  kissing: 'Kissing', eyes: 'Eye contact', tremble: 'Trembling', loud: 'Loud moans', quiet: 'Quiet moans',
  nomoan: 'No moaning', silent: 'No sound', tongue: 'Tongue out', bite: 'Biting her lip', smile: 'Smiling',
  eyesClosed: 'Eyes closed', condom: 'Condom', hold: 'Hands hold on',
};
// which extras cancel which
const CLASH = { loud: ['quiet', 'nomoan', 'silent'], quiet: ['loud', 'nomoan', 'silent'], nomoan: ['loud', 'quiet'], silent: ['loud', 'quiet'] };
export const LOOP = { min: 2, max: 12, default: 3 };

export const EXAMPLES = [
  "slow cowgirl on the sofa, she's teasing him, 5 seconds",
  "slow, tender missionary on the double bed, she's close to the edge, ends in a climax, 12 seconds",
  'rough doggy on the bed, fast, he cums inside',
  'lazy spooning in bed with kissing, 6 seconds',
  'she sits on his lap on the loveseat, passionate',
  'making out standing up, eye contact',
];
export const FOLLOW_UPS = ['rougher', 'slower', 'longer', 'add kissing', 'on the bed instead', 'doggy now', 'finish on her back', 'no finish'];

export const speedWord = v => (v <= 0.12 ? 'Very slow' : v <= 0.35 ? 'Slow' : v <= 0.65 ? 'Steady' : v <= 0.9 ? 'Fast' : 'Very fast');
export const forceWord = v => (v <= 0.3 ? 'Gentle' : v <= 0.7 ? 'Firm' : 'Hard');

// ---------------------------------------------------------------- adults only
// Refused outright (the whole sentence, before anything else looks at it). Words are matched whole (after undoing
// "l33t" spellings and stretched letters), the long ones also with one or two typos; phrases and ages are matched
// on the text. "girl" and "young adult" (the Sims life stage) are fine; "boy", "little girl", "teen..." are not.
const MINOR_WORDS = ['child', 'children', 'childs', 'childhood', 'kid', 'kids', 'kiddo', 'kiddos', 'kiddie', 'kiddies', 'kiddy', 'toddler', 'toddlers',
  'infant', 'infants', 'baby', 'babies', 'newborn', 'newborns', 'tween', 'tweens', 'minor', 'minors', 'underage', 'underaged',
  'juvenile', 'juveniles', 'adolescent', 'adolescents', 'pubescent', 'prepubescent', 'loli', 'lolis', 'lolicon', 'lolita', 'lolitas',
  'shota', 'shotas', 'shotacon', 'schoolgirl', 'schoolgirls', 'schoolboy', 'schoolboys', 'highschool', 'highschooler', 'highschoolers',
  'kindergarten', 'preschool', 'preschooler', 'boy', 'boys', 'jailbait', 'pedo', 'pedos', 'pedophile', 'pedophilia', 'paedo',
  'paedophile', 'youngster', 'youngsters', 'daughter', 'stepdaughter', 'son', 'stepson', 'cp', 'sweet sixteen', 'pubescent', 'puberty',
  'nymphet', 'girlchild', 'boychild', 'underaged', 'minorsex'];
const MINOR_PREFIX = ['teen', 'preteen', 'child', 'toddler', 'infant', 'loli', 'shota', 'pedo', 'paedo', 'underage', 'schoolgirl', 'schoolboy', 'kindergart'];
const MINOR_PHRASES = ['little girl', 'little girls', 'little boy', 'little boys', 'young girl', 'young girls', 'young boy', 'young boys', 'small girl',
  'small boy', 'high school', 'middle school', 'grade school', 'junior high', 'elementary school', 'primary school', 'school girl', 'school girls',
  'school boy', 'school boys', 'school uniform', 'under age', 'under aged', 'pre teen', 'barely legal', 'not 18', 'under 18', 'below 18',
  'younger than 18', 'not an adult', 'not adult', 'not yet 18', 'child sim', 'teen sim', 'kid sim'];
const ANIMAL_WORDS = ['dog', 'dogs', 'puppy', 'puppies', 'pup', 'pups', 'animal', 'animals', 'pet', 'pets', 'horse', 'horses', 'pony', 'beast',
  'beasts', 'bestiality', 'zoo', 'zoophilia', 'zoophile', 'canine', 'canines', 'k9', 'feline', 'kitten', 'kittens', 'livestock', 'sheep', 'goat'];
const CONSENT_WORDS = ['rape', 'raped', 'rapes', 'raping', 'rapist', 'noncon', 'nonconsent', 'nonconsensual', 'unconscious', 'drugged', 'roofied'];
const CONSENT_PHRASES = ['non consensual', 'non consent', 'passed out', 'against her will', 'against his will', 'without consent', 'no consent'];
const NUMBER_WORDS = { zero: 0, a: 1, an: 1, one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9, ten: 10, eleven: 11,
  twelve: 12, thirteen: 13, fourteen: 14, fifteen: 15, sixteen: 16, seventeen: 17, eighteen: 18, nineteen: 19, twenty: 20, thirty: 30,
  forty: 40, fifty: 50, sixty: 60, half: 0.5 };
const LEET = { 0: 'o', 1: 'i', 3: 'e', 4: 'a', 5: 's', 7: 't', 8: 'b', '@': 'a', $: 's', '!': 'i', '|': 'l' };
export const REFUSALS = {
  minors: 'Adults only. Say it never makes anything with minors - not with those words either.',
  animals: 'Adults only - people only, never animals.',
  consent: 'Only scenes between adults who both want it.',
};

// -> null, or {kind, message}
export function refuse(text) {
  const low = String(text || '').toLowerCase().normalize('NFKD').replace(/[̀-ͯ]/g, '').replace(/[’‘`´]/g, "'");
  const minor = { kind: 'minors', message: REFUSALS.minors };
  // ages under 18: "16 yo", "15-year-old", "age 12", "aged 9", "sixteen year old"
  const ageNum = '(1[0-7]|[1-9])';
  if (new RegExp(`(^|[^\\d.])${ageNum}\\s*[-_ ]?\\s*(yo|y\\/o|y\\.o\\.?|yrs?|years?|yr)\\b`).test(low)) return minor;
  if (new RegExp(`\\b(age|aged|ages)\\s*[:=]?\\s*${ageNum}\\b`).test(low)) return minor;
  const youngNumber = Object.entries(NUMBER_WORDS).filter(([w, n]) => n >= 1 && n < 18 && w.length > 2).map(([w]) => w).join('|');
  if (new RegExp(`\\b(${youngNumber})\\s*[-_ ]?\\s*(years?|yrs?|yo)\\b`).test(low)) return minor;
  // words: letters kept together with the digits and symbols people use to dodge filters
  const rough = low.split(/[^a-z0-9@$!|]+/).filter(Boolean);
  const words = rough.map(w => (/[a-z]/.test(w) && /[0-9@$!|]/.test(w) ? [...w].map(c => LEET[c] || c).join('') : w))
    .map(w => w.replace(/[^a-z0-9]/g, '')).filter(Boolean).map(w => w.replace(/(.)\1{2,}/g, '$1$1'));
  // letters typed apart: "t e e n"
  for (let i = 0; i < words.length; i++) {
    let j = i, joined = '';
    while (j < words.length && words[j].length === 1) joined += words[j++];
    if (joined.length >= 3) words.push(joined);
    if (j > i) i = j - 1;
  }
  const text2 = ' ' + words.join(' ') + ' ';
  const hasPhrase = list => list.some(p => text2.includes(' ' + p + ' '));
  if (hasPhrase(MINOR_PHRASES)) return minor;
  if (hasPhrase(CONSENT_PHRASES)) return { kind: 'consent', message: REFUSALS.consent };
  const minorSet = new Set(MINOR_WORDS), animalSet = new Set(ANIMAL_WORDS), consentSet = new Set(CONSENT_WORDS);
  const longMinor = MINOR_WORDS.filter(w => w.length >= 6);
  for (const w of words) {
    const singular = w.replace(/s$/, '');
    if (minorSet.has(w) || minorSet.has(singular) || MINOR_PREFIX.some(p => w.startsWith(p))) return minor;
    if (w.length >= 6 && longMinor.some(m => Math.abs(m.length - w.length) <= 2 && osa(w, m) <= (m.length >= 9 ? 2 : 1))) return minor;
    if (animalSet.has(w)) return { kind: 'animals', message: REFUSALS.animals };
    if (consentSet.has(w) || /^rap(e|ed|es|ing|ist)$/.test(w)) return { kind: 'consent', message: REFUSALS.consent };
  }
  return null;
}

// ---------------------------------------------------------------- the vocabulary
// [slot, value, 'phrase|phrase|...', extra]. weak phrases lose to strong ones of the same slot anywhere in the
// sentence ("oral", "head", "butt"). Dual phrases ("on her back") are a finish place when the same part of the
// sentence talks about finishing, else a position.
const V = [];
const vocab = (slot, value, phrases, extra = {}) => { for (const p of phrases.split('|')) V.push({ slot, value, phrase: p.trim().split(/\s+/), ...extra }); };

// positions
vocab('act', 'cowgirl', 'cowgirl|cowgirls|cow girl|riding|ride him|rides him|riding him|she rides|rides|ride|girl on top|woman on top|her on top|she is on top|she on top|she gets on top|bouncing on him|bounces on him|bouncing on his|straddling him|straddles him|straddling|straddle|on top of him|rides his|riding his');
vocab('act', 'cowgirl', 'reverse cowgirl|reverse cow girl|reverse', { note: 'reverse' });
vocab('act', 'missionary', 'missionary|missionary position|face to face|he is on top|he on top|him on top|man on top|guy on top|on top of her|legs up|legs in the air|legs spread|spread legs|spreads her legs|between her legs|lying on her back|lies on her back|laying on her back');
vocab('act', 'missionary', 'on her back', { dual: 'back' });
vocab('act', 'doggy', 'doggy|doggie|doggy style|doggie style|doggystyle|doggiestyle|doggy position|from behind|from the back|on all fours|all fours|on her hands and knees|hands and knees|bent over|bends over|bending over|bend over|takes her from behind');
vocab('act', 'standing', 'standing|standing up|stand up|stands|stand|on their feet|while standing');
vocab('act', 'standing', 'up against the wall|against the wall|against a wall|pinned to the wall|pinned against the wall|by the wall', { also: { place: 'wall' } });
vocab('act', 'spooning', 'spooning|spoon|spoons|spooned|on their sides|on their side|lying on their sides|lying on their side|on her side|lying on her side|side by side|sideways|from the side');
vocab('act', 'pronebone', 'prone bone|pronebone|prone|flat on her stomach|face down|lying face down|on her front|flat on her front|lying flat|flat on her belly');
vocab('act', 'pronebone', 'on her stomach|on her belly|on her tummy', { dual: 'belly' });
vocab('act', 'sitting', 'lap ride|lap|on his lap|sits on his lap|sitting on his lap|sit on his lap|in his lap|sitting on him|sits on him|sitting|seated|sit|sits|sitting down|sits down');
vocab('act', 'anal', 'anal|anally|in the ass|in her ass|in his ass|in the butt|in her butt|butt sex|ass fuck|assfuck|ass fucking|backdoor|back door|up the ass|anal sex');
vocab('act', 'anal', 'butt|ass|bum', { weak: true });
vocab('act', 'bj', 'blowjob|blowjobs|blow job|blowjob|blowie|bj|sucks him|sucking him|suck him|sucks him off|sucking him off|sucks his|sucking his|sucking|sucks|suck|giving head|gives head|give head|going down on him|goes down on him|go down on him|deepthroat|deep throat|deepthroating|deepthroats|throat|oral on him|gives him oral|giving him oral|on her knees|kneeling|kneels|kneel');
vocab('act', 'bj', 'oral|head|mouth', { weak: true });
vocab('act', 'handjob', 'handjob|handjobs|hand job|hj|handy|jerks him|jerking him|jerk him|jerks him off|jerking him off|jerk him off|jerking|jerks|strokes him|stroking him|stroke him|stroking his|strokes his|wanks him|wanking him|wanking|hand on his|jacking him off|jacks him off');
vocab('act', 'handjob', 'stroking|strokes', { weak: true });
vocab('act', 'cunni', 'cunnilingus|cunni|eats her out|eating her out|eat her out|eats her|eating her|eat her|licks her|licking her|lick her|goes down on her|going down on her|go down on her|oral on her|gives her oral|giving her oral|pussy licking|licking her pussy|licks her pussy|face sitting|facesitting|sits on his face|sitting on his face|sit on his face');
vocab('act', 'cunni', 'licking|licks|lick', { weak: true });
vocab('act', 'titjob', 'titjob|titjobs|tit job|titfuck|tit fuck|titty fuck|titty job|tittyfuck|titties job|boobjob|boob job|paizuri|between her breasts|between her tits|between her boobs|with her tits|with her boobs|with her breasts');
vocab('act', 'kiss', 'making out|make out|makes out|makeout|makeouts|snogging|snog|necking|cuddling|cuddle|cuddles|foreplay|hugging|hug|hugs|embracing|embrace|embraces');
vocab('act', 'carry', 'carry|carrying|carries her|carrying her|carried|carries|holds her up|holding her up|lifts her|lifting her|lifted|lifts her up|picks her up|picking her up|in his arms|standing carry|legs around him|legs wrapped around him|wrapped around him|up in the air');
vocab('act', 'sixtynine', '69|sixty nine|sixtynine|soixante neuf');
vocab('act', 'fingering', 'fingering|fingers her|fingering her|finger her|fingered|fingerbang|fingerbanging|finger bang|fingering herself|rubs her|rubbing her|rubbing her clit|rubs her clit|touching her|touches her|touching her pussy');
vocab('act', 'fingering', 'fingers|finger|rubbing|rubs', { weak: true });
// plain sex words: an act was asked for, but not which
vocab('generic', true, 'sex|having sex|has sex|have sex|fuck|fucks|fucking|fucked|fuck her|fucking her|fucks her|screw|screws|screwing|bang|bangs|banging|shag|shags|shagging|sleeping together|sleep together|hook up|hooking up|intercourse|penetration|penetrates|penetrating|inside her|woohoo|woo hoo|nookie');
vocab('generic', true, 'making love|make love|makes love|lovemaking|love making', { also: { mood: 'tender' } });
// places
vocab('place', 'double_bed', 'bed|beds|the bed|double bed|big bed|large bed|queen bed|king bed|queen size bed|king size bed|queen sized bed|king sized bed|kingsize bed|mattress|bedroom|in bed|master bed|doublebed');
vocab('place', 'single_bed', 'single bed|small bed|twin bed|narrow bed|little bed|cot|bunk|bunk bed|dorm bed|singlebed');
vocab('place', 'sofa', 'sofa|sofas|couch|couches|settee|living room|divan|sectional|lounge');
vocab('place', 'loveseat', 'loveseat|love seat|small sofa|small couch|two seater|little sofa|little couch|loveseats');
vocab('place', 'chair_living', 'armchair|arm chair|chair|chairs|easy chair|recliner|lounge chair|dining chair|kitchen chair|office chair|stool|armchairs');
vocab('place', 'counter', 'counter|counters|kitchen counter|countertop|counter top|kitchen|kitchen island|island|bar|bar counter|worktop|sink');
vocab('place', 'table_dining', 'table|tables|dining table|kitchen table|desk|office desk|work desk|coffee table|dinner table|desks');
vocab('place', 'floor', 'floor|floors|the floor|ground|carpet|rug|floorboards|mat|yoga mat|blanket|towel|beach towel|on the ground|on the floor|living room floor|bedroom floor');
vocab('place', 'wall', 'wall|walls');
vocab('noplace', 'shower', 'shower|showers|in the shower|hot tub|hottub|jacuzzi|bathtub|bath tub|bath|bathroom|pool|swimming pool|sauna|toilet|car|beach|outside|outdoors|park|garden|forest|woods|office|gym|balcony|elevator|lift|stairs|staircase|piano|washing machine|dryer|window|door|doorway|hallway|garage|tent|boat|train|plane|bench|porch');
// who is in it
vocab('pair', 'ff', 'two women|two woman|two girls|two ladies|lesbian|lesbians|lesbo|girl on girl|girl girl|woman on woman|woman and woman|women together|ff|f f|wlw|sapphic|her girlfriend|she and her girlfriend|with her girlfriend|two females|2 women|2 girls');
vocab('pair', 'ff', 'women|girls|ladies', { weak: true });
vocab('pair', 'mm', 'two men|two man|two guys|two males|gay|gays|guy on guy|man on man|man and man|men together|mm|m m|mlm|his boyfriend|with his boyfriend|he and his boyfriend|2 men|2 guys');
vocab('pair', 'mm', 'men|guys', { weak: true });
vocab('pair', 'futa', 'futa|futas|futanari|dickgirl|dick girl|girl with a dick|woman with a penis|girl with a penis|woman with a dick|trans woman|transwoman|trans girl|trans|shemale|with a futa|and a futa');
vocab('pair', 'couple', 'man and woman|woman and man|a man and a woman|a woman and a man|him and her|her and him|he and she|she and he|straight|husband and wife|wife and husband|boyfriend and girlfriend|girlfriend and boyfriend|guy and girl|girl and guy|guy and a girl|couple|a couple|hetero');
// moods
vocab('mood', 'tender', 'tender|tenderly|tenderness|loving|lovingly|romantic|romantically|romance|sweet|sweetly|intimate|intimately|sensual|sensually|caring|affectionate|affectionately|soft and slow|slow and sweet|gentle and slow|slow and gentle|lovey dovey|emotional');
vocab('mood', 'passionate', 'passionate|passionately|passion|steamy|hot|heated|eager|eagerly|horny|needy|lustful|lust|lusty|desperate|desperately|hungry|hungrily|intense|intensely|into it|fiery|sexy|naughty|dirty|sultry|raunchy');
vocab('mood', 'rough', 'rough|roughly|wild|wildly|aggressive|aggressively|dominant|dominating|dominates|domination|dom|brutal|brutally|fierce|fiercely|feral|savage|hardcore|kinky|animalistic|primal|rough sex|bdsm');
vocab('mood', 'teasing', 'teasing|tease|teases|teased|teasingly|flirty|flirting|flirts|flirtatious|seductive|seductively|seducing|seduces|seduce|tempting|tantalizing|tantalising|taunting|slow tease|toying with him|toying with her|playing with him|playing with her|playing hard to get');
vocab('mood', 'playful', 'playful|playfully|fun|funny|giggly|giggling|giggles|silly|cheeky|laughing|laughs|happy|joyful|goofy');
vocab('mood', 'lazy', 'lazy|lazily|sleepy|drowsy|morning|lazy morning|sunday morning|relaxed|relaxing|casual|casually|chill|chilled|lazy sunday|comfy|cozy|cosy|sluggish');
vocab('mood', 'shy', 'shy|shyly|nervous|nervously|timid|timidly|awkward|awkwardly|bashful|hesitant|hesitantly|first time|their first time|her first time|his first time|reluctant');
// speed (how fast) and strength (how hard), absolute
vocab('speed', 0.08, 'very slow|really slow|super slow|extremely slow|slow motion|slowest|very slowly|really slowly|super slowly|snail pace|painfully slow|so slow|so slowly|incredibly slow');
vocab('speed', 0.2, 'slow|slowly|nice and slow|slow pace|leisurely|unhurried|gradual|gradually|take their time|taking their time|takes their time|take her time|takes her time|take his time|takes his time|no rush|slow paced|lingering');
vocab('speed', 0.5, 'steady|steadily|medium|moderate|moderately|normal|normal speed|medium speed|medium pace|average|rhythmic|rhythmically|regular pace|steady pace|natural|naturally');
vocab('speed', 0.8, 'fast|quick|quickly|rapid|rapidly|speedy|quickie|hurried|hasty|hastily|fast paced|fast pace|brisk|briskly|energetic|energetically|vigorous|vigorously');
vocab('speed', 1, 'very fast|really fast|super fast|extremely fast|frantic|frantically|furious|furiously|jackhammer|jackhammering|jackhammers|as fast as|fastest|lightning fast|full speed|so fast|insanely fast|crazy fast');
vocab('force', 0.05, 'very gentle|really gentle|super gentle|very gently|very softly|so gentle|so gently|barely moving');
vocab('force', 0.15, 'gentle|gently|soft|softly|light|lightly|careful|carefully|delicate|delicately|shallow|shallowly|light strokes|soft strokes|gentle strokes');
vocab('force', 0.5, 'firm|firmly|medium strength|steady strokes|solid');
vocab('force', 0.9, 'hard|deep|deeply|pounding|pounds|pound|slamming|slams|slam|balls deep|powerful|powerfully|forceful|forcefully|strong|strongly|thrusting hard|hard and deep|deep and hard|rail|railing|rails her|pounding her|pounds her|slams her|hard strokes|deep strokes');
vocab('force', 1, 'very hard|really hard|super hard|extremely hard|as hard as|so hard|brutally hard');
// relative changes (follow-ups)
vocab('forceRel', 1, 'rougher|harder|more rough|more roughly|wilder|more intense|more force|more aggressive|deeper|stronger|more power|more powerful|heavier|turn it up|step it up|kick it up|kick it up a notch|more hardcore|more wild');
vocab('forceRel', -1, 'gentler|softer|more gentle|more gently|lighter|less rough|less hard|less intense|calmer|tone it down|tone down|easier|go easy|take it easy|less aggressive|less force|more tender|more loving|shallower|less deep|more softly|more carefully');
vocab('speedRel', 1, 'faster|quicker|more speed|speed up|speed it up|pick up the pace|pick up the speed|hurry|hurry up|more quickly|up the tempo|up the pace|faster pace|quicker pace|more fast');
vocab('speedRel', -1, 'slower|slow down|slow it down|less speed|less fast|more slowly|ease off|ease up|calm down|bring it down|slower pace|not so fast|not as fast');
vocab('lenRel', 1.5, 'longer|make it longer|lengthen|extend|extend it|more time|stretch it|longer loop|longer animation|a longer loop');
vocab('lenRel', 1 / 1.5, 'shorter|make it shorter|shorten|shorten it|less time|shorter loop|trim it|cut it down|shorter animation|a shorter loop');
vocab('lenRel', 2, 'twice as long|double the length|double length|double it|two times longer|two times as long');
vocab('lenRel', 0.5, 'half as long|half the length|half length|cut it in half');
vocab('len', 2.5, 'short|brief|short loop|quick loop|shortest');
vocab('len', 8, 'long|lengthy|long loop|long animation|longest');
// the finish
vocab('finish', 'auto', 'climax|climaxes|climaxing|climaxed|orgasm|orgasms|orgasming|cum|cums|cumming|cummed|came|finish|finishes|finishing|finished|ends in a climax|ending in a climax|ends with a climax|ending with a climax|end in a climax|ends in climax|until he cums|until they cum|ejaculates|ejaculation|ejaculating|nut|nuts|busts|bust a nut|blows his load|climax at the end|cumshot|cumshots|money shot|he cums|he comes|he finishes|he climaxes|he orgasms|comes|cum shot|jizz|load');
vocab('finish', 'her', "she cums|she comes|she climaxes|she orgasms|she finishes|her orgasm|she has an orgasm|she has orgasm|makes her cum|make her cum|making her cum|makes her come|make her come|she squirts|squirt|squirts|squirting|until she cums|until she comes|her climax");
vocab('finish', 'inside', 'inside|inside her|cums inside|cum inside|comes inside|finishes inside|finish inside|cumming inside|creampie|creampies|cream pie|fills her|filling her|fills her up|filling her up|cums in her|comes in her|cum in her|in her pussy');
vocab('finish', 'face', 'facial|facials|on her face|on his face|all over her face|in her mouth|in his mouth|in mouth|swallows|swallow|swallowing|cum in mouth|cum in her mouth|down her throat|cum on her face|cums on her face|finishes on her face|finish on her face');
vocab('finish', 'chest', 'on her chest|on her tits|on her boobs|on her breasts|on his chest|all over her tits|on her titties|cum on her tits|cums on her tits');
vocab('finish', 'belly', 'on his belly|on his stomach|pulls out|pull out|pulling out|pullout|cum on her belly|cums on her belly');
vocab('finish', 'back', 'on his back|all over her back|cums on her back|cum on her back|finish on her back|finishes on her back');
vocab('finish', 'butt', 'on her ass|on her butt|on his ass|on her bum|on his butt|on her cheeks|cum on her ass|cums on her ass');
vocab('finish', 'feet', 'on her feet|on his feet|on her toes|cum on her feet');
vocab('finish', 'none', 'no finish|no climax|no orgasm|no cum|no cumming|without finishing|without cumming|endless|keeps going|never ends|loop forever|forever|no ending|no end|just the loop|keep looping', { exact: true });
vocab('build', true, 'close to the edge|on the edge|edging|edge|edged|edges|about to cum|about to come|almost cumming|almost coming|almost there|close to cumming|close to coming|getting close|nearly there|building up|builds up|build up|builds to|building to|on the brink|near climax|close to climax|close to orgasm|about to climax|close to finishing|close to it|nearly cumming|close');
// extras
vocab('extra', 'kissing', 'kissing|kiss|kisses|kissed|kisses her|kisses him|kissing her|kissing him|kissing each other|kiss each other|lips locked|tongue kissing|french kissing|french kiss|kissing her neck|kisses her neck|neck kissing|smooching|smooch|smooches|kissy');
vocab('extra', 'eyes', 'eye contact|looking at each other|look at each other|looks at each other|looking into each other|looking into her eyes|looking into his eyes|looks into her eyes|looks into his eyes|staring at each other|gazing|gazes|gaze|staring|stares|looking at him|looks at him|looking at her|looks at her|looking back|looks back|looks back at him|looking back at him|watching each other|watches him|watching him|watches her|watching her');
vocab('extra', 'tremble', 'trembling|trembles|tremble|trembly|shaking|shakes|shaky|shaking legs|legs shaking|legs shake|quivering|quivers|quiver|twitching|twitches|spasms|shuddering|shudders|shudder');
vocab('extra', 'loud', 'loud|loudly|screaming|screams|scream|noisy|vocal|moaning loudly|moans loudly|moaning loud|moans a lot|lots of moaning|yelling|shouting|crying out|cries out|louder|more moaning|more moans|more noise|moan more|moans more|loud moans');
vocab('extra', 'quiet', 'quiet|quietly|soft moans|whisper|whispers|whispering|muffled|hushed|stifled|softly moaning|moaning softly|moans softly|little moans|small moans|quieter|less moaning|less moans|less noise|moan less|more quiet|more quietly|gentle moans|quiet moans');
vocab('extra', 'silent', 'silent|silently|no sound|no sounds|without sound|without sounds|mute|muted|no audio|no noise|in silence|without any sound|sound off');
vocab('extra', 'nomoan', 'no moaning|no moans|without moaning|no voices|no voice|without voices|no talking', { exact: true });
vocab('extra', 'moan', 'moaning|moans|moan|moaned|groaning|groans|groan|panting|pants|gasping|gasps|breathing heavily|heavy breathing|breathless|sighing|sighs');
vocab('extra', 'tongue', 'tongue out|tongue|tongues|ahegao|rolling eyes|eyes rolling|eyes roll back|eyes rolled back|mouth open|open mouth|drooling|drools');
vocab('extra', 'bite', 'biting her lip|bites her lip|bite her lip|biting his lip|bites his lip|lip bite|lip biting|biting lip|bites lip|lip bites|biting her lips|bites her lips');
vocab('extra', 'smile', 'smiling|smile|smiles|grinning|grin|grins|smirking|smirks|smirk');
vocab('extra', 'eyesClosed', 'eyes closed|eyes shut|closed eyes|shut eyes|with her eyes closed|with closed eyes|eyes tightly shut|closes her eyes|closing her eyes|closes his eyes');
vocab('extra', 'condom', 'condom|condoms|with a condom|wearing a condom|rubber|protection|protected|safe sex|safely|wrapped up');
vocab('extra', '-condom', 'bareback|barebacking|no condom|without a condom|without condom|raw|no protection|unprotected', { exact: true });
vocab('extra', 'hold', 'hands on her hips|hands on hips|holding her hips|holds her hips|grabbing her hips|grabs her hips|grips her hips|gripping her hips|holding her waist|holds her waist|grabbing her waist|grabs her waist|grabbing her ass|grabs her ass|grabbing her butt|grabs her butt|holding her|holds her|holding each other|holds each other|hands on her|grabbing her|grabs her|hands on him|holding him|holds him');
// what Say it does not make (recognised, so it can say so)
vocab('nope', 'group', 'threesome|threesomes|foursome|group|group sex|orgy|gangbang|gang bang|three of them|3some|mmf|ffm|mff|fmm|spitroast|spit roast|double penetration|dp');
vocab('nope', 'solo', 'solo|alone|masturbating|masturbates|masturbation|masturbate|by herself|by himself|on her own|on his own|jerking off|jerks off|jacking off');
vocab('nope', 'dance', 'dance|dances|dancing|lap dance|lapdance|pole dance|pole dancing|striptease|strip tease|stripping|strips|stripper|twerk|twerking|twerks');
vocab('nope', 'toy', 'toy|toys|dildo|dildos|vibrator|vibrators|sex toy|sex toys|strapon|strap on|strap-on|plug|butt plug');
// follow-up words
vocab('cue', 'instead', 'instead|rather|instead of that|now|switch|switch to|change|change to|change it|make it|make them|swap to|go to|move to|move them to|let them|then|also|too|as well|plus|add|put them|put it');
vocab('reroll', true, 'again|redo|try again|one more time|once more|replay|same again|do it again|another take');
vocab('surprise', true, 'surprise me|surprise|random|anything|whatever|you pick|you choose|up to you|something else|different|another position|other position|something different|dealers choice|any');
vocab('fresh', true, 'new|start over|from scratch|new one|new scene|fresh|restart|start again|brand new|new animation');

const NEGATORS = new Set(['no', 'not', 'without', 'never', 'stop', 'remove', 'minus', 'drop', 'lose', 'skip', 'nor', 'neither', 'less', 'cancel', 'delete']);
const NEG_PHRASES = [['get', 'rid', 'of'], ['take', 'out'], ['take', 'away'], ['turn', 'off'], ['no', 'more'], ['leave', 'out']];
const MORE = new Set(['more', 'extra', 'lots', 'even', 'lot']);
const BIG = new Set(['much', 'way', 'lot', 'lots', 'far', 'really', 'very', 'super', 'extremely', 'even', 'waaay', 'loads', 'heaps', 'tons']);
const SMALL = new Set(['bit', 'little', 'slightly', 'tad', 'touch', 'somewhat', 'tiny', 'smidge', 'slight']);
const SHE = new Set(['she', 'her', 'woman', 'girl', 'wife', 'girlfriend', 'lady', 'hers', 'herself', 'female', 'gf']);
const HE = new Set(['he', 'him', 'man', 'guy', 'husband', 'boyfriend', 'dude', 'his', 'himself', 'male', 'bf']);
const SEPARATORS = new Set([',', '.', ';', '!', '?', ':', 'but', 'then', 'while', 'whilst']);
const UNITS = { s: 1, sec: 1, secs: 1, second: 1, seconds: 1, seconde: 1, sek: 1, m: 60, min: 60, mins: 60, minute: 60, minutes: 60, f: 1 / 30, frame: 1 / 30, frames: 1 / 30 };
// small words that are never "not understood" and never spell-fixed
const STOP = new Set(('a an the and or but with on in at of to for from by into onto over under up down is are am be been being was were it its '
  + 'this that these those then than so very really too just some while as she he her him his hers they them their theirs we us our i me my '
  + 'you your make makes making made want wants like please let lets have has having had get gets getting got do does doing did can could '
  + 'would should will shall one each other another both together bit little lot lots more less much now again instead also kind sort '
  + 'scene animation anim animations loop loops looping long time way style position positions pose poses there here all around about '
  + 'go goes going gets give gives giving take takes taking put puts where when who what which how if into onto upon off out after before '
  + 'during until till still even ever maybe quite rather pretty somewhat sure okay ok yes yeah hey hi hello thanks thank sims sim woman man '
  + 'women men girl guy lady wife husband girlfriend boyfriend partner lover lovers couple person people body bodies both them same one ones '
  + 'something someone somebody thing things stuff moment moments second seconds s sec secs minute minutes min mins frame frames '
  + 'hands hand legs leg arms arm eyes eye lips lip mouth face neck hips hip waist ass butt tits boobs breasts chest back feet foot '
  + 'dick cock penis pussy vagina clit balls wet wetter wettest cute nice good great best better beautiful pretty gorgeous hot '
  + 'looking look looks see seeing watch watching keep keeps kept first last next end ends ending start starts starting begin begins '
  + 'again whole full half every each any few many most least other others').split(/\s+/));
// ordinary words that must never be "fixed" into a vocabulary word ("show" is not "slow", "well" is not "wall")
const COMMON = new Set(('show shows showing snow slot slots slew glow well will walk walks walking tall ball call mean means main mane moon '
  + 'loan beyond chain chains coach cough touch touches touching tablet stable cable hard card herd yard harm head heads heat heated hear '
  + 'heart fist fast last past vast mast cast list lost slam slim slip slips ship shop shot shut chat hat fat bat mat rat sat vat pat '
  + 'sofa soda soft sort port post most must mist fist feet feed fees seed seen seem sleep sleeps sleeping sleeper deep deer peer beer '
  + 'bear beard bread break broke brake bake cake lake make made fade wade wide wine wind wild mild mile mild milk silk sick side '
  + 'slide slides glide ride rider riders rides rode road read real reel roll rolls role rule rules rude room rooms roof hook look '
  + 'book cook took tool pool cool fool food good goad gold hold holds cold told tell tells sell cell bell belly tall tale male mail '
  + 'nail rail tail sail fail pail pale page wage cage rage race face lace pace place places space spice slice price prize '
  + 'rough tough though through thought tongue tone tones stone store story more mode made mood moody moan mean '
  + 'kinds kind find mind minds bind blind blend bland brand grand stand stands sand band hand hands land lend send bend '
  + 'lets bets gets sets pets wets vets jets nets best rest test west nest vest zest jest text next '
  + 'sweat sweet sweets street treat trees tree three free freeze breeze please pleased pleasure pleasures leisure measure '
  + 'love loves loved lover lovely live lives lived give gives given alive above move moves moved moving movie '
  + 'bedside bedtime beside inside outside aside besides decide decides maybe baby gravy navy wavy heavy '
  + 'toward towards forward backwards afterwards upward downward sideway anyway anyways always away sway sways swaying '
  + 'while whole white write wrote quite quiet quit suit fruit shirt skirt dress dressed naked nude undress undressed clothes clothed '
  + 'lingerie underwear panties bra jeans stockings heels boots socks topless shirtless').split(/\s+/));

// Vocabulary words for the spelling fixer (4+ letters) and the phrase index (first word -> entries, longest first)
const VOCAB_WORDS = new Set();
const INDEX = new Map();
for (const e of V) {
  for (const w of e.phrase) if (w.length >= 4 && !/^\d+$/.test(w)) VOCAB_WORDS.add(w);
  const k = e.phrase[0];
  if (!INDEX.has(k)) INDEX.set(k, []);
  INDEX.get(k).push(e);
}
for (const list of INDEX.values()) list.sort((a, b) => b.phrase.length - a.phrase.length);
const VOCAB_LIST = [...VOCAB_WORDS];

// Optimal string alignment distance (Levenshtein + swapped neighbours: "cowgril" -> "cowgirl" is 1).
export function osa(a, b) {
  const n = a.length, m = b.length;
  if (!n) return m;
  if (!m) return n;
  let p2 = null, p1 = Array.from({ length: m + 1 }, (_, j) => j);
  for (let i = 1; i <= n; i++) {
    const cur = [i];
    for (let j = 1; j <= m; j++) {
      const c = a[i - 1] === b[j - 1] ? 0 : 1;
      let d = Math.min(p1[j] + 1, cur[j - 1] + 1, p1[j - 1] + c);
      if (p2 && i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) d = Math.min(d, p2[j - 2] + 1);
      cur.push(d);
    }
    p2 = p1; p1 = cur;
  }
  return p1[m];
}

// The nearest vocabulary word for a word nobody knows, or null. 4-5 letters: one typo; 6-8: two; 9+: three.
// The first letter must match (a typo there is rare), except for a single slip in a long word ("kowgirl").
const _fixCache = new Map();
export function fixSpelling(w) {
  if (w.length < 4 || VOCAB_WORDS.has(w) || STOP.has(w) || COMMON.has(w) || /\d/.test(w)) return null;
  if (_fixCache.has(w)) return _fixCache.get(w);
  const most = w.length <= 5 ? 1 : w.length <= 8 ? 2 : 3;
  let best = null, bestD = Infinity;
  for (const v of VOCAB_LIST) {
    if (Math.abs(v.length - w.length) > most) continue;
    const d = osa(w, v);
    if (d > most) continue;
    if (v[0] !== w[0] && !(d === 1 && w.length >= 6)) continue;
    const score = d + (v[0] === w[0] ? 0 : 0.5) + Math.abs(v.length - w.length) * 0.1;
    if (score < bestD) { bestD = score; best = v; }
  }
  _fixCache.set(w, best);
  return best;
}

// ---------------------------------------------------------------- words in
const SPLIT = { dont: ['do', 'not'], doesnt: ['does', 'not'], didnt: ['did', 'not'], isnt: ['is', 'not'], arent: ['are', 'not'], wont: ['will', 'not'],
  cant: ['can', 'not'], cannot: ['can', 'not'], shouldnt: ['should', 'not'], wouldnt: ['would', 'not'], shes: ['she', 'is'], hes: ['he', 'is'],
  im: ['i', 'am'], theyre: ['they', 'are'], lets: ['let', 'us'], gonna: ['going', 'to'], wanna: ['want', 'to'], w: ['with'], wo: ['without'] };
export function tokenize(text) {
  let s = String(text || '').toLowerCase().normalize('NFKD').replace(/[̀-ͯ]/g, '')
    .replace(/[’‘`´]/g, "'").replace(/&/g, ' and ').replace(/\+/g, ' and ').replace(/\//g, ' ');
  s = s.replace(/(\d)\s*[-–]\s*(?=[a-z])/g, '$1 ').replace(/(\d)([a-z])/g, '$1 $2').replace(/([a-z])(\d)/g, '$1 $2');
  s = s.replace(/\bcan't\b/g, 'can not').replace(/\bwon't\b/g, 'will not').replace(/n't\b/g, ' not')
    .replace(/\b(she|he|it|that|there|what|who)'s\b/g, '$1 is').replace(/'re\b/g, ' are').replace(/'ll\b/g, ' will')
    .replace(/'ve\b/g, ' have').replace(/'d\b/g, ' would').replace(/'m\b/g, ' am').replace(/'s\b/g, '').replace(/'/g, '');
  const out = [];
  for (const t of s.match(/\d+(?:\.\d+)?|[a-z]+|[,.;!?:]/g) || []) {
    if (SPLIT[t]) out.push(...SPLIT[t]);
    else out.push(t.replace(/(.)\1{2,}/g, '$1$1'));      // "sloooow" -> "sloow" (the fixer does the rest)
  }
  return out;
}

const num = t => (/^\d+(\.\d+)?$/.test(t) ? parseFloat(t) : (t in NUMBER_WORDS ? NUMBER_WORDS[t] : null));

// ---------------------------------------------------------------- the parser
const blankSpec = () => ({ act: null, place: null, pair: null, mood: null, moodBy: null, speed: null, force: null, seconds: null,
  finish: null, build: false, extras: {}, reverse: false });

// Read one sentence. current: the spec of the scene that is open (for follow-ups), or null.
// -> {refused, message, spec, delta, fresh, empty, unknown: [word], fixes: [[typed, read]], notes: [{text, warn}],
//     changes: [text], reroll, surprise}
export function parse(text, { current = null } = {}) {
  const out = { refused: null, message: '', spec: null, delta: blankSpec(), fresh: true, empty: true, unknown: [], fixes: [], notes: [],
    changes: [], reroll: false, surprise: false, text: String(text || '').trim() };
  const no = refuse(text);
  if (no) { out.refused = no.kind; out.message = no.message; return out; }
  const raw = tokenize(text);
  // spelling: a word nobody knows becomes the nearest vocabulary word
  const toks = raw.map(t => {
    if (SEPARATORS.has(t) || /^\d/.test(t) || INDEX.has(t) || STOP.has(t) || COMMON.has(t) || NEGATORS.has(t) || t in UNITS || t in NUMBER_WORDS) return t;
    const f = fixSpelling(t);
    if (f) { out.fixes.push([t, f]); return f; }
    return t;
  });
  // clauses (for "not", "on her back" and who does what)
  const clause = [];
  let c = 0;
  for (const t of toks) { if (SEPARATORS.has(t)) c++; clause.push(c); }
  // 1. phrases, longest first
  const hits = [];
  const used = new Array(toks.length).fill(false);
  for (let i = 0; i < toks.length; i++) {
    const list = INDEX.get(toks[i]);
    if (!list) continue;
    const e = list.find(x => x.phrase.every((w, k) => toks[i + k] === w && !SEPARATORS.has(toks[i + k])));
    if (!e) continue;
    hits.push({ e, i, n: e.phrase.length, clause: clause[i] });
    for (let k = 0; k < e.phrase.length; k++) used[i + k] = true;
    i += e.phrase.length - 1;
  }
  // 2. lengths: "5 seconds", "a 10 second loop", "half a minute", "2 seconds longer", "120 frames"
  const d = out.delta;
  for (let i = 0; i < toks.length; i++) {
    if (used[i]) continue;
    let n = num(toks[i]), j = i + 1;
    if (n === null) continue;
    if (toks[i] === 'half' && toks[j] === 'a') j++;
    else if (toks[j] === 'and' && toks[j + 1] === 'a' && toks[j + 2] === 'half') { n += 0.5; j += 3; }
    const unit = UNITS[toks[j]];
    if (unit === undefined) {
      // a lone number: 69 is a position (a phrase); others are left for "not understood"
      if (toks[i] === 'a' || toks[i] === 'an' || toks[i] === 'half') continue;
      continue;
    }
    if (toks[i] === 'a' && toks[j] === 'second') continue;   // "a second position"
    let secs = n * unit;
    used[i] = true; for (let k = i + 1; k <= j; k++) used[k] = true;
    const after = toks[j + 1], before = toks[i - 1], before2 = toks[i - 2];
    if (after === 'longer' || after === 'more' || before === 'add' || (before === 'by' && before2 === 'longer')) {
      d.lenAdd = (d.lenAdd || 0) + secs; if (after === 'longer' || after === 'more') used[j + 1] = true;
    } else if (after === 'shorter' || after === 'less' || (before === 'by' && before2 === 'shorter')) {
      d.lenAdd = (d.lenAdd || 0) - secs; if (after === 'shorter' || after === 'less') used[j + 1] = true;
    } else d.seconds = secs;
    i = j;
  }
  // relative lengths "longer by 2 seconds" leave their "longer" hit in: drop it when a number already did it
  // 3. the hits, in order
  const negated = h => {
    // a "no", "not", "without"... up to three words before, in the same part of the sentence (a comma, "and" or
    // "but" ends it)
    for (let k = h.i - 1, seen = 0; k >= 0 && seen < 3; k--) {
      const t = toks[k];
      if (SEPARATORS.has(t) || t === 'and' || t === 'with') return false;
      if (NEGATORS.has(t) && t !== 'less') return true;
      if (NEG_PHRASES.some(p => p.every((w, q) => toks[k - p.length + 1 + q] === w))) return true;
      // another word of the sentence in between ends it - but not a filler like "too" or "now" ("not too fast")
      if (hits.some(x => x !== h && x.e.slot !== 'cue' && k >= x.i && k < x.i + x.n)) return false;
      seen++;
    }
    return false;
  };
  const lessBefore = h => { for (let k = h.i - 1; k >= Math.max(0, h.i - 3); k--) { if (toks[k] === 'less') return true; if (SEPARATORS.has(toks[k])) break; } return false; };
  const moreBefore = h => { for (let k = h.i - 1; k >= Math.max(0, h.i - 3); k--) { if (MORE.has(toks[k])) return true; if (SEPARATORS.has(toks[k])) break; } return false; };
  const amount = h => {
    let f = 1;
    for (let k = h.i - 1; k >= Math.max(0, h.i - 3); k--) {
      if (BIG.has(toks[k])) f = Math.max(f, 1.6);
      if (SMALL.has(toks[k])) f = Math.min(f, 0.5);
      if (SEPARATORS.has(toks[k])) break;
    }
    return f;
  };
  const who = h => {
    // the person doing it: the nearest "she"/"he" before it in the same part of the sentence, else after it
    for (let k = h.i - 1; k >= 0 && clause[k] === h.clause; k--) { if (SHE.has(toks[k])) return 'FEMALE'; if (HE.has(toks[k])) return 'MALE'; }
    return null;
  };
  const finishInClause = cl => hits.some(x => x.clause === cl && x.e.slot === 'finish' && x.e.value !== 'none');
  const strong = { act: false, pair: false };
  for (const h of hits) if ((h.e.slot === 'act' || h.e.slot === 'pair') && !h.e.weak && !h.e.dual) strong[h.e.slot] = true;
  let actWeight = -1;
  for (const h of hits) {
    const e = h.e, neg = e.exact ? false : negated(h);
    const say = t => out.changes.push(t);
    switch (e.slot) {
      case 'act': {
        if (e.dual && finishInClause(h.clause)) { if (!neg) d.finish = e.dual; break; }
        if (e.weak && strong.act) break;
        if (neg) { out.notes.push({ text: `Left out: not ${ACTS[e.value].label.toLowerCase()}` }); break; }
        // "on top": who is on top decides
        const w = e.weak ? 0 : e.dual ? 1 : 2;
        if (w > actWeight || (w === actWeight && !d.act)) { d.act = e.value; actWeight = w; d.reverse = e.note === 'reverse'; }
        if (e.also && e.also.place) d.placeHint = e.also.place;
        break;
      }
      case 'generic': d.generic = true; if (e.also && e.also.mood && !d.mood) d.mood = e.also.mood; break;
      case 'place': if (!neg) d.place = e.value; else out.notes.push({ text: `Left out: not the ${(PLACES[e.value] || e.value).toLowerCase()}` }); break;
      case 'noplace': if (!neg) out.notes.push({ text: `No ${e.phrase.join(' ')} to put them in yet - pick another place`, warn: true, missingPlace: e.phrase.join(' ') }); break;
      case 'pair': if (e.weak && strong.pair) break; if (!neg) d.pair = e.value; break;
      case 'mood': {
        if (neg) { if (e.value === 'rough' || e.value === 'passionate') { d.forceRel = (d.forceRel || 0) - 0.3; say('not ' + e.value); } break; }
        if (lessBefore(h)) {
          const m = MOODS[e.value];
          d.forceRel = (d.forceRel || 0) + (m.force > 0.5 ? -0.25 : 0.25); d.speedRel = (d.speedRel || 0) + (m.speed > 0.5 ? -0.2 : 0.2);
          say('less ' + e.value); break;
        }
        d.mood = e.value;
        const by = who(h);
        if (by) d.moodBy = by;
        if (moreBefore(h)) { d.moodMore = true; say('more ' + e.value); }
        break;
      }
      case 'speed': {
        if (neg) { d.speed = e.value >= 0.5 ? 0.35 : 0.65; say(`not ${speedWord(e.value).toLowerCase()}`); break; }
        if (moreBefore(h) || lessBefore(h)) { const s = (e.value >= 0.5 ? 1 : -1) * (lessBefore(h) ? -1 : 1); d.speedRel = (d.speedRel || 0) + 0.25 * s * amount(h); say(s > 0 ? 'faster' : 'slower'); break; }
        d.speed = e.value; break;
      }
      case 'force': {
        if (neg) { d.force = e.value >= 0.5 ? 0.35 : 0.65; say(`not ${forceWord(e.value).toLowerCase()}`); break; }
        if (moreBefore(h) || lessBefore(h)) { const s = (e.value >= 0.5 ? 1 : -1) * (lessBefore(h) ? -1 : 1); d.forceRel = (d.forceRel || 0) + 0.25 * s * amount(h); say(s > 0 ? 'harder' : 'gentler'); break; }
        d.force = e.value; break;
      }
      case 'forceRel': d.forceRel = (d.forceRel || 0) + 0.25 * e.value * amount(h) * (neg ? -1 : 1); say(e.phrase.join(' ')); break;
      case 'speedRel': d.speedRel = (d.speedRel || 0) + 0.25 * e.value * amount(h) * (neg ? -1 : 1); say(e.phrase.join(' ')); break;
      case 'lenRel': if (d.lenAdd === undefined) { d.lenMul = (d.lenMul || 1) * (neg ? 1 / e.value : e.value); say(e.phrase.join(' ')); } break;
      case 'len': if (d.seconds === null && d.lenAdd === undefined) d.seconds = e.value; break;
      case 'finish': {
        if (e.value === 'none' || neg) { d.finish = 'none'; break; }
        if (e.value === 'auto') { if (!d.finish || d.finish === 'none') d.finish = 'auto'; }
        else if (e.value === 'her') { if (!d.finish || d.finish === 'none' || d.finish === 'auto') d.finish = 'her'; }
        else d.finish = e.value;
        break;
      }
      case 'build': if (!neg) d.build = true; else d.noBuild = true; break;
      case 'extra': {
        if (e.value === '-condom') { d.extras.condom = false; break; }
        if (neg || lessBefore(h)) {
          if (e.value === 'moan') d.extras.nomoan = true;
          else if (e.value === 'loud') d.extras.quiet = true;
          else d.extras[e.value] = false;
        } else d.extras[e.value] = true;
        break;
      }
      case 'nope': out.notes.push({ text: { group: 'Say it makes scenes for two sims', solo: 'Say it makes scenes for two sims', dance: 'Dances are not part of Say it', toy: 'Toys are not part of Say it yet' }[e.value], warn: true }); break;
      case 'cue': d.cue = true; break;
      case 'reroll': out.reroll = true; d.cue = true; break;
      case 'surprise': out.surprise = true; break;
      case 'fresh': d.fresh = true; break;
      default: break;
    }
  }
  // "on top" with nobody named: she is (the most common meaning)
  // 4. words it did not understand (the ordinary small words are skipped)
  toks.forEach((t, i) => {
    if (used[i] || SEPARATORS.has(t) || STOP.has(t) || COMMON.has(t) || NEGATORS.has(t) || MORE.has(t) || BIG.has(t) || SMALL.has(t) || SHE.has(t) || HE.has(t)) return;
    if (t.length < 3 && !/^\d/.test(t)) return;
    out.unknown.push(raw[i]);
  });
  out.unknown = [...new Set(out.unknown)];
  // 5. fresh scene or a change to the open one
  const given = ['act', 'place', 'pair', 'mood', 'speed', 'force', 'seconds', 'finish'].filter(k => d[k] !== null && d[k] !== undefined);
  const extrasGiven = Object.keys(d.extras).length;
  const anything = given.length + extrasGiven + (d.build ? 1 : 0) + (d.forceRel || d.speedRel || d.lenMul || d.lenAdd ? 1 : 0) + (out.reroll || out.surprise ? 1 : 0) + (d.generic ? 1 : 0);
  out.empty = !anything;
  out.fresh = !current || !!d.fresh || (!d.cue && !!d.act && given.length >= 3);
  const base = out.fresh ? blankSpec() : JSON.parse(JSON.stringify(current));
  if (!base.extras) base.extras = {};
  const spec = base;
  for (const k of ['act', 'place', 'pair', 'finish']) if (d[k] !== null && d[k] !== undefined) spec[k] = d[k];
  if (d.act) spec.reverse = !!d.reverse;
  if (d.placeHint && !d.place) spec.place = d.placeHint;
  if (d.mood) {
    spec.mood = d.mood; spec.moodBy = d.moodBy || null;
    // a new mood brings its own speed and strength, unless the sentence says them
    if (d.speed === null) spec.speed = null;
    if (d.force === null) spec.force = null;
  }
  if (d.speed !== null) spec.speed = d.speed;
  if (d.force !== null) spec.force = d.force;
  if (d.seconds !== null) spec.seconds = d.seconds;
  if (d.build) spec.build = true;
  if (d.noBuild) spec.build = false;
  for (const [k, v] of Object.entries(d.extras)) {
    if (v) { spec.extras[k] = true; for (const x of CLASH[k] || []) delete spec.extras[x]; }
    else delete spec.extras[k];
  }
  // "kissing" with no position at all: they make out
  if (!spec.act && d.extras.kissing && !d.generic) { spec.act = 'kiss'; delete spec.extras.kissing; }
  // relative changes work from what is there now (the mood's own numbers when none were set)
  const eff = resolveNumbers(spec);
  if (d.moodMore) { spec.force = clamp01(eff.force + 0.15); spec.speed = clamp01(eff.speed + 0.1); }
  if (d.forceRel) spec.force = clamp01(eff.force + d.forceRel);
  if (d.speedRel) spec.speed = clamp01(eff.speed + d.speedRel);
  if (d.lenMul) spec.seconds = eff.seconds * d.lenMul;
  if (d.lenAdd) spec.seconds = eff.seconds + d.lenAdd;
  if (spec.seconds !== null) {
    const want = spec.seconds;
    spec.seconds = Math.round(Math.min(LOOP.max, Math.max(LOOP.min, want)) * 2) / 2;
    if (want > LOOP.max + 0.01) out.notes.push({ text: `${LOOP.max} s is the longest loop` });
    if (want < LOOP.min - 0.01) out.notes.push({ text: `${LOOP.min} s is the shortest loop` });
  }
  out.spec = spec;
  return out;
}

const clamp01 = x => Math.round(Math.min(1, Math.max(0, x)) * 100) / 100;

// Speed, strength and loop length as they will be made (the mood's own when the sentence did not say).
export function resolveNumbers(spec) {
  const m = spec.mood && MOODS[spec.mood];
  return {
    speed: spec.speed !== null && spec.speed !== undefined ? spec.speed : m ? m.speed : 0.55,
    force: spec.force !== null && spec.force !== undefined ? spec.force : m ? m.force : 0.55,
    seconds: spec.seconds !== null && spec.seconds !== undefined ? spec.seconds : LOOP.default,
  };
}

// ---------------------------------------------------------------- filling in what was not said
// env: {acts: [ids Magic can make now], places: [{id, label, kind}] (app.furniture)}
// -> the spec with every field set, and auto: {field: true} for the ones picked for the user
export function resolve(spec, env = {}) {
  const r = JSON.parse(JSON.stringify(spec || blankSpec()));
  r.extras = r.extras || {};
  const auto = {};
  const acts = (env.acts && env.acts.length ? env.acts : Object.keys(ACTS)).filter(a => ACTS[a]);
  const places = env.places && env.places.length ? env.places : Object.keys(PLACES).map(id => ({ id, label: PLACES[id] }));
  const hasPlace = id => places.some(p => p.id === id);
  const placeKind = id => (places.find(p => p.id === id) || {}).kind || (id === 'floor' ? 'floor' : /bed/.test(id) ? 'bed' : /sofa|loveseat/.test(id) ? 'sofa' : '');
  if (r.place && !hasPlace(r.place)) {
    const fall = r.place === 'wall' ? 'floor' : /bed/.test(r.place) ? 'double_bed' : 'floor';
    r.placeNote = `${PLACES[r.place] || r.place} is not there - used the ${placeLabel(fall, places).toLowerCase()}`;
    r.place = hasPlace(fall) ? fall : places[0] && places[0].id;
  }
  if (!r.act || !acts.includes(r.act)) {
    if (r.act && !acts.includes(r.act)) r.actNote = `${ACTS[r.act].label} is not in your library - made another position`;
    const k = r.place ? placeKind(r.place) : '';
    const byMood = { rough: 'doggy', lazy: 'spooning', teasing: 'cowgirl', playful: 'cowgirl', tender: 'missionary', passionate: 'missionary', shy: 'missionary' };
    const want = r.place === 'wall' || k === 'counter' || k === 'table' ? 'standing'
      : ['sofa', 'armchair'].includes(k) ? 'sitting'
        : (r.mood && byMood[r.mood]) || 'missionary';
    r.act = acts.includes(want) ? want : acts.includes('missionary') ? 'missionary' : acts[0];
    auto.act = true;
  }
  if (!r.place) {
    const want = ACTS[r.act].place;
    r.place = hasPlace(want) ? want : hasPlace('floor') ? 'floor' : places[0].id;
    auto.place = true;
  }
  if (!r.pair) { r.pair = 'couple'; auto.pair = true; }
  const n = resolveNumbers(r);
  if (r.speed === null || r.speed === undefined) { r.speed = n.speed; auto.speed = true; }
  if (r.force === null || r.force === undefined) { r.force = n.force; auto.force = true; }
  if (r.seconds === null || r.seconds === undefined) { r.seconds = n.seconds; auto.seconds = true; }
  if (!r.finish) { r.finish = 'none'; auto.finish = true; }
  // a plain "climax": where this act's finish goes; "she comes" in an act where only he can: her orgasm
  r.finishPart = r.finish === 'auto' ? ACTS[r.act].finish : r.finish;
  if (r.finishPart === 'inside' && !ACTS[r.act].pen && r.act !== 'bj' && r.act !== 'sixtynine') r.finishPart = ACTS[r.act].finish;
  // two women: a finish with cum needs the strap-on's partner to... have none - it becomes her orgasm
  if (r.pair === 'ff' && !['none', 'her'].includes(r.finishPart)) r.finishPart = 'her';
  r.auto = auto;
  return r;
}

export function placeLabel(id, places) {
  const p = (places || []).find(x => x.id === id);
  return (p && p.label) || PLACES[id] || String(id || '').replace(/_/g, ' ');
}

// ---------------------------------------------------------------- the plan for Magic
// -> makeMagic options (web/js/magic.js): recipe, place, speed, force, seconds, bodies, finish, faces, voices, sounds,
// look, kissing, tremble, condom, eyesMix, name
export function toMagic(spec, env = {}) {
  const r = resolve(spec, env);
  const act = ACTS[r.act], mood = r.mood && MOODS[r.mood];
  const x = r.extras || {};
  const busy = role => act.mouth === 'BOTH' || act.mouth === role;
  const kissing = !!x.kissing && !!act.kiss;
  const oneTime = !['none', 'her'].includes(r.finishPart);
  const herPeak = r.build || r.finishPart === 'her' || oneTime;
  // faces over the loop, per part: [[t 0..1, preset], ...]
  const faces = {};
  const plan = (role, list, peak) => {
    if (busy(role)) return;
    let seq = [...list];
    if (role === 'FEMALE') {
      if (x.bite) seq[0] = 'bite';
      if (x.smile) seq[0] = 'smile';
    } else if (x.smile) seq[0] = 'smile';
    let tl;
    if (oneTime) {
      // a one-time climax: it builds, peaks at the finish (70 %) and calms down after
      tl = [[0, seq[0]], [0.38, seq[1] || seq[0]], [0.62, peak], [0.8, peak], [0.96, 'relaxed']];
    } else if (peak) {
      tl = [[0, seq[0]], [0.4, seq[1] || seq[0]], [0.72, peak]];
    } else tl = seq.map((f, k) => [k / seq.length, f]);
    if (kissing) {
      // lips meet twice a loop
      const add = oneTime ? [0.2] : [0.25, 0.75];
      tl = [...tl.filter(([t]) => !add.some(a => Math.abs(a - t) < 0.08)), ...add.map(t => [t, 'kiss'])].sort((a, b) => a[0] - b[0]);
    }
    faces[role] = tl;
  };
  const moodFaces = mood ? mood.faces : null;
  const teaserIs = mood && mood.teaser ? (r.moodBy || 'FEMALE') : null;
  const facesOf = role => {
    if (!moodFaces) return null;
    if (teaserIs) return teaserIs === role ? moodFaces[0] : moodFaces[1];
    return role === 'FEMALE' ? moodFaces[0] : moodFaces[1];
  };
  const tongue = x.tongue ? 'ahegao' : 'ecstasy';
  for (const role of ['FEMALE', 'MALE']) {
    const seq = facesOf(role);
    const peak = role === 'FEMALE' ? (herPeak ? tongue : null) : (oneTime ? 'ecstasy' : null);
    if (seq) plan(role, seq, peak);
    else if (peak || kissing || (x.tongue && role === 'FEMALE')) plan(role, [null], peak || (x.tongue && role === 'FEMALE' ? 'ahegao' : null));
  }
  // voices: [set, every] per part, 'none' for no voices
  let voices = null;
  if (x.silent || x.nomoan) voices = 'none';
  else if (mood || x.loud || x.quiet || kissing) {
    voices = {};
    for (const [k, role] of [[0, 'FEMALE'], [1, 'MALE']]) {
      const base = mood ? mood.voice[k] : null;
      if (busy(role)) { voices[role] = role === 'MALE' ? { set: 'breath', every: 4 } : null; continue; }
      let set = base ? base[0] : null, every = base ? base[1] : null;
      if (x.loud) { set = role === 'FEMALE' ? 'moan' : set || 'woohoo'; every = Math.max(1.4, (every || 2.5) * 0.6); }
      if (x.quiet) { set = role === 'FEMALE' ? 'moan_soft' : 'breath'; every = (every || 3.5) * 1.8; }
      if (kissing && role === 'FEMALE' && (!mood || ['tender', 'teasing', 'shy', 'playful', 'lazy'].includes(r.mood))) set = 'kiss';
      voices[role] = set ? { set, every: every || 3 } : undefined;
    }
  }
  const moodWord = mood ? mood.label + ' ' : '';
  const name = `${moodWord}${moodWord ? act.label.toLowerCase() : act.label}`.replace(/^69$/, 'Sixty-nine').replace(/^(\w)/, s => s.toUpperCase());
  return {
    recipe: r.act, place: r.place, seconds: r.seconds, speed: r.speed, force: r.force, intensity: (r.speed + r.force) / 2,
    bodies: [...(PAIRS[r.pair] || PAIRS.couple).bodies], finish: oneTime ? r.finishPart : 'none', faces, voices,
    sounds: !x.silent, eyeContact: !!x.eyes || kissing, kissing, tremble: !!x.tremble || r.build || r.finishPart === 'her',
    condom: !!x.condom, eyesMix: x.eyesClosed ? { FEMALE: { eyes: 0.95 } } : null, name, resolved: r,
  };
}

// ---------------------------------------------------------------- what it understood, as chips
// -> [{slot, label, text, auto, warn, remove}] (remove: the chip can be taken away)
export function chipsFor(spec, env = {}) {
  const r = resolve(spec, env);
  const out = [];
  const places = env.places;
  out.push({ slot: 'act', label: 'Position', text: ACTS[r.act].label + (r.reverse ? ' (reverse: made facing him)' : ''), auto: !!r.auto.act });
  out.push({ slot: 'place', label: 'Place', text: placeLabel(r.place, places), auto: !!r.auto.place });
  if (r.pair !== 'couple' || !r.auto.pair) out.push({ slot: 'pair', label: 'Who', text: PAIRS[r.pair].label, auto: !!r.auto.pair });
  if (r.mood) out.push({ slot: 'mood', label: 'Mood', text: MOODS[r.mood].label + (MOODS[r.mood].teaser ? (r.moodBy === 'MALE' ? ' (him)' : ' (her)') : ''), remove: true });
  out.push({ slot: 'speed', label: 'Speed', text: speedWord(r.speed), auto: !!r.auto.speed });
  out.push({ slot: 'force', label: 'Strength', text: forceWord(r.force), auto: !!r.auto.force });
  out.push({ slot: 'seconds', label: 'Loop', text: `${r.seconds} s`, auto: !!r.auto.seconds });
  if (r.finish !== 'none') out.push({ slot: 'finish', label: 'Finish', text: FINISHES[r.finishPart] || r.finishPart, remove: true });
  if (r.build) out.push({ slot: 'build', label: '', text: 'Close to the edge', remove: true });
  for (const k of Object.keys(r.extras || {})) {
    if (!r.extras[k] || !EXTRAS[k]) continue;
    const warn = k === 'kissing' && !ACTS[r.act].kiss;
    out.push({ slot: 'extra:' + k, label: '', text: EXTRAS[k] + (warn ? ` - faces too far apart in ${ACTS[r.act].label.toLowerCase()}` : ''), remove: true, warn });
  }
  if (r.placeNote) out.push({ slot: 'note', label: '', text: r.placeNote, warn: true });
  if (r.actNote) out.push({ slot: 'note', label: '', text: r.actNote, warn: true });
  return out;
}

// The choices a chip offers when clicked: [{value, label}]
export function choicesFor(slot, env = {}) {
  const acts = env.acts && env.acts.length ? env.acts : Object.keys(ACTS);
  if (slot === 'act') return acts.filter(a => ACTS[a]).map(a => ({ value: a, label: ACTS[a].label }));
  if (slot === 'place') return (env.places && env.places.length ? env.places : Object.keys(PLACES).map(id => ({ id, label: PLACES[id] })))
    .map(p => ({ value: p.id, label: p.label }));
  if (slot === 'pair') return Object.entries(PAIRS).map(([value, p]) => ({ value, label: p.label }));
  if (slot === 'mood') return [{ value: null, label: 'No mood' }, ...Object.entries(MOODS).map(([value, m]) => ({ value, label: m.label }))];
  if (slot === 'speed') return [0.08, 0.2, 0.5, 0.8, 1].map(value => ({ value, label: speedWord(value) }));
  if (slot === 'force') return [0.15, 0.5, 0.9].map(value => ({ value, label: forceWord(value) }));
  if (slot === 'seconds') return [2, 3, 4, 5, 6, 8, 10, 12].map(value => ({ value, label: value + ' s' }));
  if (slot === 'finish') return Object.entries(FINISHES).map(([value, label]) => ({ value, label }));
  return [];
}

// Change one field of a spec from a chip (value null takes a removable chip away). -> a new spec
export function setField(spec, slot, value) {
  const s = JSON.parse(JSON.stringify(spec || blankSpec()));
  s.extras = s.extras || {};
  if (slot.startsWith('extra:')) { const k = slot.slice(6); if (value) s.extras[k] = true; else delete s.extras[k]; return s; }
  if (slot === 'build') { s.build = !!value; return s; }
  if (slot === 'mood') { s.mood = value || null; s.moodBy = null; s.speed = null; s.force = null; return s; }
  if (slot === 'finish') { s.finish = value || 'none'; return s; }
  if (slot === 'act') { s.act = value; s.reverse = false; return s; }
  if (slot in s) s[slot] = value;
  return s;
}

// A short sentence for what a follow-up changed ("Rougher and longer").
export function describeChanges(before, after, env = {}) {
  if (!before) return '';
  const a = resolve(before, env), b = resolve(after, env), out = [];
  if (a.act !== b.act) out.push(ACTS[b.act].label.toLowerCase());
  if (a.place !== b.place) out.push('on the ' + placeLabel(b.place, env.places).toLowerCase());
  if (a.pair !== b.pair) out.push(PAIRS[b.pair].label.toLowerCase());
  if (a.mood !== b.mood) out.push(b.mood ? MOODS[b.mood].label.toLowerCase() : 'no mood');
  if (Math.abs(a.force - b.force) > 0.01) out.push(b.force > a.force ? 'harder' : 'gentler');
  if (Math.abs(a.speed - b.speed) > 0.01) out.push(b.speed > a.speed ? 'faster' : 'slower');
  if (a.seconds !== b.seconds) out.push(`${b.seconds} s loop`);
  if (a.finishPart !== b.finishPart) out.push(b.finishPart === 'none' ? 'no finish' : 'finish: ' + (FINISHES[b.finishPart] || b.finishPart).toLowerCase());
  if (a.build !== b.build) out.push(b.build ? 'close to the edge' : 'not on the edge');
  for (const k of new Set([...Object.keys(a.extras || {}), ...Object.keys(b.extras || {})])) {
    if (!!a.extras[k] !== !!b.extras[k] && EXTRAS[k]) out.push((b.extras[k] ? '+ ' : '- ') + EXTRAS[k].toLowerCase());
  }
  const s = out.join(', ');
  return s ? s[0].toUpperCase() + s.slice(1) : '';
}
