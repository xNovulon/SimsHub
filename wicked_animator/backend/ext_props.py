"""Props (spec_bodies 10): the objects WickedWhims animations let sims hold or stand in the scene.

    GET /api/props                  -> [{guid, objName, name, uses, source: 'game'|'mods'}]  (objmesh.prop_list:
                                       every prop the animation library uses that the game or Mods has, adults only,
                                       most used first; guids are strings - 64-bit ids do not fit a JS number)
    GET /api/props?missing=1        -> {'ids': [library animation ids that need a prop pack],
                                        'detail': {id: {'guids', 'parked': [packs in Mods_parked that have them]}}}
    GET /api/prop_mesh?guid=<id>    -> objmesh.object_mesh(guid): the prop's meshes in its transformBone rest frame
                                       (the rig origin), textures from /api/furniture_tex

Also props_missing(anim) for the library list (server.py _library: "needs a prop pack").
"""
import threading
import traceback

import objmesh


def _props(q):
    if str(q.get('missing', '')).lower() in ('1', 'true', 'yes'):
        detail = objmesh.missing_props()
        _ready.set()
        return {'ids': sorted(detail), 'detail': {str(k): v for k, v in detail.items()}}
    items = objmesh.prop_list()
    _ready.set()
    return items


def _prop_mesh(q):
    raw = str(q.get('guid', '')).strip()
    if not raw.isdigit():
        raise ValueError('Which prop? (guid=<number>)')
    guid = int(raw)
    if not objmesh.prop_ok(guid):
        raise LookupError('That prop is not in the game or in your Mods folder.')
    try:
        return objmesh.object_mesh(guid)
    except (KeyError, ValueError) as ex:
        raise LookupError(str(ex) or 'That prop has no mesh.')


def props_missing(anim):
    """True when a library animation ({'id', 'props'?}) needs a prop that neither the game nor Mods has. Never raises
    and never waits: False until the prop list is ready (it is made in the background at start)."""
    try:
        if not anim.get('props') or not _ready.is_set():
            return False
        return bool(objmesh.props_missing(anim['id']))
    except Exception:
        return False


_ready = threading.Event()


def _warm():
    try:
        objmesh.prop_list()
    except Exception:
        traceback.print_exc()
    finally:
        _ready.set()


GET = {'props': _props, 'prop_mesh': _prop_mesh}
WARM = [_warm]
