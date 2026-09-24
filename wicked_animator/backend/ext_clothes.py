"""Clothes in the preview (to check clipping with outfits), read-only on the game and Mods folders. Preview only:
clothes never go into an exported animation.

    GET /api/clothes_outfits?tray=<id>&index=<i>
          an adult Tray sim's outfits: {name, current, outfits: [{key, category, label, index, parts: [{casp,
          body_type, body_type_name, kind, name, origin}]}]}  (origin null: that part isn't installed)
    GET /api/clothes_basic?frame=yf|ym|yf_futa
          a few base-game outfits for the plain bodies: {items: [{id, label, parts: [{casp, name, body_type, kind}]}]}
    GET /api/clothes_part?casp=0x...[&shape_tray=<id>&shape_index=<i>]
          one CAS part as meshes: {casp, name, origin, body_type, kind, meshes: [{positions, normals, uvs, faces, bones,
          weights}], texture, cache}  (origin null and no meshes: not installed; 'painted': the game paints it on the
          skin, so there is no mesh). shape_tray puts it on that Tray sim's body shape, as /api/hair does.
    GET /api/clothes_tex?file=clothes_<key>.png   a part's diffuse texture (only files clothes.py wrote)
"""


def _plain(fn):
    """A missing game folder answers 404 'The Sims 4 install not found', like the other game routes."""
    def run(q):
        try:
            return fn(q)
        except FileNotFoundError as ex:
            raise LookupError(str(ex) or 'The Sims 4 install not found')
    return run


def _outfits(q):
    import clothes
    if not q.get('tray'):
        raise ValueError('Ask for a Tray sim with tray= and index=.')
    return clothes.tray_outfits(q['tray'], int(q.get('index', 0)))


def _basic(q):
    import clothes
    frame = q.get('frame', 'yf')
    if frame not in ('yf', 'ym', 'yf_futa'):
        raise LookupError('unknown body')
    return {'frame': frame, 'items': clothes.basic_outfits(frame)}


def _part(q):
    import clothes, hair
    if not q.get('casp'):
        raise ValueError('Ask for a CAS part with casp=.')
    shape = hair.tray_spec(q['shape_tray'], q.get('shape_index', 0)) if q.get('shape_tray') else None
    try:
        return clothes.part_mesh(q['casp'], shape)
    except (TypeError, ValueError) as ex:
        raise ValueError(str(ex) or 'bad CAS part')


def _tex(q):
    import clothes
    path = clothes.texture_path(q.get('file'))
    if not path:
        raise LookupError('no texture')
    with open(path, 'rb') as f:
        return f.read(), 'image/png'


GET = {'clothes_outfits': _plain(_outfits), 'clothes_basic': _plain(_basic), 'clothes_part': _plain(_part),
       'clothes_tex': _tex}
