"""The app with the stand-in game (tools/checks/lib/fake_game_server.py) plus SYNTHETIC clothes, for the Clothes
control's browser check (ui_smoke.js). Nothing is read from or written to a game, Mods or Tray folder: the parts live
in two packages in a temp folder, built with synth.py.

    ANIMATOR_PORT=8793 python tools/checks/clothes/clothes_server.py

On top of fake_game_server.py:
  - morph.PART_INDEX reads only the temp "game" package: tubes around the stand-in rig's chest, hips and feet (a tee,
    jeans, sneakers, a bra and briefs, a necklace, boxers for the man) with one-colour textures, and tights that have
    no mesh (painted on the skin in the game);
  - casptex.casp_by_name / load_casp answer from those parts (the basic outfits are found in them by name);
  - one adult Tray sim, "Test Sim" (tray 0x01, index 0), with an everyday, a swimwear and a formal outfit (the formal
    one lists a part that is not installed), whose body is the stand-in woman's (no body sliders);
  - body sliders resolve to nothing (morph.resolve_morphs), so shaped parts are the plain ones.
The real clothes.py, ext_clothes.py and hair.py code reads the parts, maps the skinning and writes the cache.
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TMP = tempfile.mkdtemp(prefix='wa_clothes_ui_')
os.environ.setdefault('WA_FAKE_HOME', os.path.join(TMP, 'home'))
sys.path.insert(0, os.path.join(HERE, '..', 'lib'))
sys.path.insert(0, HERE)
import fake_game_server as F       # noqa: E402  (swaps in the stand-in rig and bodies)
import casptex                     # noqa: E402
import hair                        # noqa: E402
import morph                       # noqa: E402
import server                      # noqa: E402
import wwpackage                   # noqa: E402
from clipfmt import fnv32          # noqa: E402
from synth import T_CASP, T_GEOM, T_DDS, make_casp, make_dds, make_geom, solid, ring_mesh, point_parts_at  # noqa: E402

ADULT_F, ADULT_M = 0x2000 | 0x10 | 0x20 | 0x40, 0x1000 | 0x10 | 0x20 | 0x40
RIG = F.fake_rig()
WORLD = F._world(RIG)
IDX = {b['name']: k for k, b in enumerate(RIG['bones'])}
NOT_INSTALLED = 0x7E57000000009999
TRAY_ID = '0x0000000000000001'


def tube(y0, y1, r, bone_lo, bone_hi, x=0.0, z=0.0, segments=12):
    """A tube skinned to one bone at the bottom ring and another at the top ring."""
    pos, faces, nrm = ring_mesh(y0, y1, r, segments, x, z)
    hashes = sorted({fnv32(bone_lo), fnv32(bone_hi)})
    lo, hi = hashes.index(fnv32(bone_lo)), hashes.index(fnv32(bone_hi))
    bones = [(lo, 0, 0, 0)] * segments + [(hi, 0, 0, 0)] * segments
    return pos, faces, nrm, bones, hashes


def geom_of(*tubes):
    pos, faces, nrm, bones, hashes = [], [], [], [], []
    for p, f, n, b, hs in tubes:
        remap = []
        for hsh in hs:
            if hsh not in hashes:
                hashes.append(hsh)
            remap.append(hashes.index(hsh))
        base = len(pos)
        pos += p; nrm += n; faces += [base + k for k in f]
        bones += [(remap[x[0]], 0, 0, 0) for x in b]
    return make_geom(pos, bones, [(1, 0, 0, 0)] * len(pos), hashes, faces, normals=nrm)


def build():
    foot_l, foot_r = WORLD[IDX['b__L_Foot__']], WORLD[IDX['b__R_Foot__']]
    shoes = lambda: geom_of(tube(foot_l[1] - 0.06, foot_l[1] + 0.04, 0.07, 'b__L_Foot__', 'b__L_Foot__', foot_l[0], 0.04),
                            tube(foot_r[1] - 0.06, foot_r[1] + 0.04, 0.07, 'b__R_Foot__', 'b__R_Foot__', foot_r[0], 0.04))
    parts = [  # (instance, name, body type, age/gender, geom bytes or None, colour)
        (0x7E57000000000001, 'yfTop_TestTee_Red', 6, ADULT_F, geom_of(tube(1.08, 1.46, 0.2, 'b__Spine1__', 'b__Spine2__')), (200, 40, 60)),
        (0x7E57000000000002, 'yfBottom_TestJeans_Blue', 7, ADULT_F, geom_of(tube(0.62, 1.07, 0.19, 'b__L_Thigh__', 'b__Pelvis__')), (40, 70, 160)),
        (0x7E57000000000003, 'yfShoes_TestSneaker_White', 8, ADULT_F, shoes(), (235, 235, 235)),
        (0x7E57000000000004, 'yfTop_TestBra_Black', 6, ADULT_F, geom_of(tube(1.22, 1.34, 0.2, 'b__Spine2__', 'b__Spine2__')), (20, 20, 24)),
        (0x7E57000000000005, 'yfBottom_TestUnderwear_Black', 7, ADULT_F, geom_of(tube(0.92, 1.03, 0.19, 'b__Pelvis__', 'b__Pelvis__')), (20, 20, 24)),
        (0x7E57000000000006, 'yfAcc_TestNecklace_Gold', 12, ADULT_F, geom_of(tube(1.46, 1.5, 0.07, 'b__Neck__', 'b__Neck__')), (220, 180, 60)),
        (0x7E57000000000007, 'yfTights_Test_Black', 42, ADULT_F, None, (10, 10, 10)),
        (0x7E57000000000011, 'ymTop_TestTee_Grey', 6, ADULT_M, geom_of(tube(1.08, 1.46, 0.21, 'b__Spine1__', 'b__Spine2__')), (120, 120, 130)),
        (0x7E57000000000012, 'ymBottom_TestJeans_Grey', 7, ADULT_M, geom_of(tube(0.62, 1.07, 0.2, 'b__L_Thigh__', 'b__Pelvis__')), (60, 60, 70)),
        (0x7E57000000000013, 'ymShoes_TestSneaker_Grey', 8, ADULT_M, shoes(), (200, 200, 200)),
        (0x7E57000000000014, 'ymBottom_TestBoxer_Grey', 7, ADULT_M, geom_of(tube(0.92, 1.03, 0.2, 'b__Pelvis__', 'b__Pelvis__')), (90, 90, 100)),
    ]
    res, casps, names = [], {}, {}
    for inst, name, bt, ag, geom, colour in parts:
        g_inst, t_inst = inst ^ 0x100000000, inst ^ 0x200000000
        tex = (T_DDS, 0, t_inst)
        if geom is not None:
            data = make_casp(name, bt, ag, [(0, [0])], [(T_GEOM, 0, g_inst), tex], diffuse=1)
            res.append((T_GEOM, 0, g_inst, geom))
        else:
            data = make_casp(name, bt, ag, [], [tex], diffuse=0)
        res += [(T_CASP, 0, inst, data), (T_DDS, 0, t_inst, make_dds(solid(*colour)))]
        casps[inst], names[name] = data, inst
    game = os.path.join(TMP, 'game', 'Data', 'Client', 'ClientFullBuild0.package')
    os.makedirs(os.path.dirname(game), exist_ok=True)
    with open(game, 'wb') as f:
        f.write(wwpackage.build_package(res))
    sims = os.path.join(TMP, 'sims')
    os.makedirs(os.path.join(sims, 'Mods'), exist_ok=True)
    point_parts_at(TMP, sims, game)
    return casps, names


CASPS, NAMES = build()


def _load_casp(key, ww=True):
    inst = NAMES.get(key) if isinstance(key, str) else key
    d = CASPS.get(inst)
    if not d:
        return None
    c = casptex.parse_casp(d)
    c['instance'], c['package'] = inst, 'ClientFullBuild0.package'
    return c


def _outfit(cat, idx, parts):
    return {'category': cat, 'category_id': 0, 'index': idx,
            'parts': [{'casp_instance': '0x%016x' % i, 'body_type': bt, 'body_type_name': str(bt)} for i, bt in parts]}


def _tray_spec(tray_id, index):
    if int(str(tray_id), 16) != 1 or int(index) != 0:
        raise KeyError('no such Tray sim')
    return {'tray_id': TRAY_ID, 'sim_index': 0, 'name': 'Test Sim', 'age': 'adult', 'species': 'human', 'gender': 'female',
            'frame': 'yf', 'prefix': 'yf', 'physique': {}, 'modifiers': [], 'sculpts': [],
            'outfits': [_outfit('EVERYDAY', 0, [(0x7E57000000000077, 2), (0x7E57000000000001, 6), (0x7E57000000000002, 7),
                                                (0x7E57000000000003, 8), (0x7E57000000000006, 12), (0x7E57000000000007, 42)]),
                        _outfit('BATHING', 0, [(0x198C, 6), (0x1990, 7)]),
                        _outfit('SWIMWEAR', 0, [(0x7E57000000000004, 6), (0x7E57000000000005, 7)]),
                        _outfit('FORMAL', 0, [(NOT_INSTALLED, 5), (0x7E57000000000003, 8)])],
            'current_outfit': {'category': 'EVERYDAY', 'index': 0}, 'hair_part': None}


def _tray_sim(self, tray_id, index):
    spec = _tray_spec(tray_id, index)
    body = F.fake_body('yf')
    return {'frame': 'yf', 'name': spec['name'], 'gender': 'female', 'age': 'adult', 'tone': '', 'toneStandIn': True,
            'toneInfo': {'status': 'standin', 'source': 'default', 'used': '', 'reason': 'missing', 'package': None},
            'body': {'frame': 'yf', 'rig': 'au', 'meshes': body['meshes'], 'ww': False}}


casptex.casp_by_name = lambda: dict(NAMES)
casptex.load_casp = _load_casp
hair.tray_spec = _tray_spec
morph.resolve_morphs = lambda spec, age_gender='yf', include_face=True: ([], {'missing': [], 'smods': 0, 'sculpts': 0, 'physique': 0})
server.Handler._tray_sim = _tray_sim

if __name__ == '__main__':
    server.main()
