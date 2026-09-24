// Writes the full-body BVH fixtures for bvh_check.mjs (tools/checks/mocap/fixtures/*.bvh). They are in git; run this
// again only after changing lib/bvhgen.mjs:   node tools/checks/mocap/make_fixtures.mjs
// (arm3_zxy.bvh and arm3_xyz.bvh are written by hand and not touched here.) Also writes fixtures/test_rig.json, the
// synthetic rig the browser smoke test serves as /api/rig.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { useThree } from './lib/three.mjs';

await useThree();
const G = await import('./lib/bvhgen.mjs');
const { makeRig } = await import('./lib/rig.mjs');
const DIR = path.join(path.dirname(fileURLToPath(import.meta.url)), 'fixtures');
fs.mkdirSync(DIR, { recursive: true });

export const FIXTURES = {
  // the reference: Mixamo names with fingers, T-pose, Y up, centimetres, 30 fps, ZXY channels
  'body_mixamo_tpose.bvh': { names: 'mixamo' },
  // the same motion: another rest pose, axes and units, frame rates and channel orders
  'body_mixamo_apose.bvh': { names: 'mixamo', apose: true },
  'body_mixamo_zup_metres.bvh': { names: 'mixamo', zUp: true, metres: true, order: 'XYZ', rootOrder: 'XYZ' },
  'body_mixamo_60fps.bvh': { names: 'mixamo', fps: 60 },
  'body_mixamo_24fps.bvh': { names: 'mixamo', fps: 24 },
  'body_mixamo_4s.bvh': { names: 'mixamo', seconds: 4 },            // two cycles of the motion (for the loop)
  // no fingers, other skeletons
  'body_mixamo_nofingers.bvh': { names: 'mixamo', fingers: false },
  'body_cmu_120fps.bvh': { names: 'cmu', fingers: false, fps: 120, order: 'ZYX', rootOrder: 'ZYX' },
  'body_daz.bvh': { names: 'daz', fingers: false, order: 'YXZ' },
  'body_biped.bvh': { names: 'biped', fingers: false },
  'body_deepmotion.bvh': { names: 'deepmotion', fingers: false, order: 'XZY' },
  'body_kinect.bvh': { names: 'kinect', fingers: false },
};

for (const [name, opts] of Object.entries(FIXTURES)) {
  const text = G.writeBVH(opts);
  fs.writeFileSync(path.join(DIR, name), text);
  console.log(name.padEnd(30), (text.length / 1024).toFixed(1) + ' KB');
}
fs.writeFileSync(path.join(DIR, 'test_rig.json'), JSON.stringify(makeRig({ full: true })));
console.log('test_rig.json');
