#!/usr/bin/env python3
"""Rebuild the complete piano as one Minecraft 1.21.11 item model.

Source: every cuboid/UV from BarkanPiano's four original mcfunctions and the
matching vanilla client block models. No angle snapping, AABB baking, omission,
or geometry simplification. Original matrices are rounded to four decimals;
length-prioritized orthogonalization removes only that export noise (<0.0001
block). Every emitted cuboid is reconstructed independently from its JSON and
compared with all eight original world vertices before the build succeeds.

The installed model is a composite of one fixed body and 88 up/down key pairs.
custom_model_data.flags[MIDI - 21] selects each pressed key, so polyphony needs
one server entity. grand_full is the complete idle geometry for review.

Model coordinates: q = 8 + 16*K*(world-C). world is relative to the original
mcfunction root, piano origin minus 0.5. All elements use the 1.21.11 XYZ
rotation format: Rz(z) * Ry(y) * Rx(x). UVs remain in the original cube frame.

After all geometry checks succeed, remove only the twelve obsolete
grand_axis/grand_r1..r5 model/item files. Existing texture files are preserved.
"""
import argparse
import base64
import copy
import hashlib
import json
import math
import os
import re
import struct
import uuid
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOME = Path.home()
DEFAULT_JAR = HOME / 'development/barkan-chess/upstream/BarkanPiano-1.20.0.jar'
DEFAULT_CLIENT = HOME / 'Library/Application Support/minecraft/versions/1.21.11/1.21.11.jar'
DEFAULT_DESC = HOME / 'development/barkan-chess/tools/piano-single.json'
MODEL_DIR = ROOT / 'assets/barkan/models/piano'
ITEM_DIR = ROOT / 'assets/barkan/items/piano'
TEX_DIR = ROOT / 'assets/barkan/textures/block/piano'
# Non-marker armor stand rider attachment adds the adult height, 1.975 blocks.
# Lower its origin so the seated player remains at the original marker seat.
SEAT = {'x': 1.46875, 'y': -0.451, 'z': 1.35}
K = 0.425
VERTEX_TOLERANCE = 0.0001
# 1.21.11 ArmorStandRenderer + CustomHeadLayer, adult/yaw180/headPose0:
# helmet world = seat + (0, 1.6885, 0) + .625 * head_transform(q/16 - .5).
# head translation JSON is in 1/16 units, hence its inverse factor 16/.625.
PASSENGER = re.compile(r'\{id:"minecraft:block_display",block_state:\{Name:"([^"]+)",Properties:\{([^}]*)\}\},transformation:\[([^\]]+)\]\}')
DIRS = ('down', 'up', 'north', 'south', 'west', 'east')


def mmul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def mvec(a, v):
    return [sum(a[i][k] * v[k] for k in range(3)) for i in range(3)]


def apply4(v, p):
    return [sum(v[r*4+c] * p[c] for c in range(3)) + v[r*4+3] for r in range(3)]


def rotation(x, y, z):
    x, y, z = map(math.radians, (x, y, z))
    cx, sx, cy, sy, cz, sz = math.cos(x), math.sin(x), math.cos(y), math.sin(y), math.cos(z), math.sin(z)
    return [[cz*cy, cz*sy*sx-sz*cx, cz*sy*cx+sz*sx],
            [sz*cy, sz*sy*sx+cz*cx, sz*sy*cx-cz*sx], [-sy, cy*sx, cy*cx]]


def euler(r):
    y = math.asin(max(-1., min(1., -r[2][0])))
    if abs(math.cos(y)) > 1e-7:
        x, z = math.atan2(r[2][1], r[2][2]), math.atan2(r[1][0], r[0][0])
    else:
        x, z = math.atan2(-r[1][2], r[1][1]), 0.
    return [round(math.degrees(a), 9) for a in (x, y, z)]


def cuboid_axes(a, extent):
    """Prefer long edges: never amplify a thin edge's four-decimal rounding."""
    cols = [[a[r][c] for r in range(3)] for c in range(3)]
    norm = lambda c: math.sqrt(sum(x*x for x in c))
    order = sorted(range(3), key=lambda i: norm(cols[i])*extent[i], reverse=True)
    basis = {}
    for i in order:
        w = cols[i][:]
        for u in basis.values():
            dot = sum(w[k]*u[k] for k in range(3))
            w = [w[k]-dot*u[k] for k in range(3)]
        length = norm(w)
        if length < 1e-12:
            raise ValueError('Degenerate source transform')
        basis[i] = [v/length for v in w]
    r = [[basis[c][row] for c in range(3)] for row in range(3)]
    det = sum(r[0][i] * (r[1][(i+1)%3]*r[2][(i+2)%3]-r[1][(i+2)%3]*r[2][(i+1)%3]) for i in range(3))
    if det < .999999:
        raise ValueError('Reflected source transform is not supported')
    return r, [sum(cols[i][row]*basis[i][row] for row in range(3)) for i in range(3)]


def load_pieces(jar):
    pieces, hashes = [], {}
    with zipfile.ZipFile(jar) as z:
        for fi in range(1, 5):
            name = f'models/grand-piano-1013-{fi}.mcfunction'
            raw = z.read(name); hashes[Path(name).name] = hashlib.sha1(raw).hexdigest()
            text = raw.decode('utf-8-sig')
            if not text.startswith('summon block_display ~-0.5 ~-0.5 ~-0.5 {Passengers:['):
                raise ValueError(f'Unexpected root in {name}')
            matches = PASSENGER.findall(text)
            if len(matches) != text.count('id:"minecraft:block_display"'):
                raise ValueError(f'Incomplete parsing in {name}')
            for index, (block, props, transform) in enumerate(matches):
                properties = dict(kv.replace('"', '').split(':') for kv in props.split(',') if kv)
                pieces.append({'file': fi, 'index': index, 'name': block, 'props': properties,
                               'm': [float(x.rstrip('f')) for x in transform.split(',')]})
    return pieces, hashes


class Vanilla:
    def __init__(self, client):
        self.z = zipfile.ZipFile(client)

    def read(self, name):
        return json.loads(self.z.read(name))

    def model(self, mid):
        textures, elements = {}, None
        while mid:
            d = self.read('assets/minecraft/models/' + mid.removeprefix('minecraft:') + '.json')
            for key, value in d.get('textures', {}).items():
                textures.setdefault(key, value)
            if elements is None and 'elements' in d:
                elements = d['elements']
            mid = d.get('parent')
        if elements is None:
            raise ValueError('Source model has no elements')
        return elements, textures

    def variant(self, piece):
        bs = self.read('assets/minecraft/blockstates/' + piece['name'].removeprefix('minecraft:') + '.json')
        for condition, value in bs['variants'].items():
            want = dict(kv.split('=') for kv in condition.split(',') if kv)
            if all(piece['props'].get(k) == v for k, v in want.items()):
                return value[0] if isinstance(value, list) else value
        raise ValueError(f'Missing blockstate {piece}')

    @staticmethod
    def resolve(textures, key):
        for _ in range(20):
            if not key.startswith('#'):
                return key.removeprefix('minecraft:')
            key = textures[key[1:]]
        raise ValueError('Texture reference cycle')


def auto_uv(face, f, t):
    return {'down': [f[0],16-t[2],t[0],16-f[2]], 'up': [f[0],f[2],t[0],t[2]],
            'north': [16-t[0],16-t[1],16-f[0],16-f[1]], 'south': [f[0],16-t[1],t[0],16-f[1]],
            'west': [f[2],16-t[1],t[2],16-f[1]], 'east': [16-t[2],16-t[1],16-f[2],16-f[1]]}[face]


def source_elements(vanilla, pieces):
    result = []
    for p in pieces:
        var = vanilla.variant(p)
        if var.get('uvlock'):
            raise ValueError('Source uvlock needs explicit handling')
        B = rotation(-var.get('x',0), -var.get('y',0), -var.get('z',0))
        elements, tex = vanilla.model(var['model'])
        for ei, e in enumerate(elements):
            if e.get('rotation'):
                raise ValueError('Source element rotation needs explicit handling')
            A = [[p['m'][r*4+c] for c in range(3)] for r in range(3)]
            extent = [(e['to'][i]-e['from'][i])/16 for i in range(3)]
            R, scale = cuboid_axes(mmul(A,B), extent)
            center = [(e['from'][i]+e['to'][i])/32 for i in range(3)]
            world = lambda q: apply4(p['m'], [x+.5 for x in mvec(B,[x-.5 for x in q])])
            faces = {}
            for direction, face in e['faces'].items():
                if 'tintindex' in face:
                    raise ValueError('Source tint needs explicit handling')
                texture = Vanilla.resolve(tex, face['texture'])
                faces[direction] = {'uv': face.get('uv', auto_uv(direction,e['from'],e['to'])), 'texture':texture}
                if face.get('rotation'):
                    faces[direction]['rotation'] = face['rotation']
            original = [world([e['to' if bit else 'from'][i]/16 for i,bit in enumerate((x,y,z))])
                        for x in (0,1) for y in (0,1) for z in (0,1)]
            result.append({'piece':p, 'element_index':ei, 'center':world(center), 'angles':euler(R),
                           'size':[extent[i]*scale[i] for i in range(3)], 'faces':faces,
                           'source_vertices':original, 'shade':e.get('shade',True)})
    return result


def make_model(elements, center, head=None, y_shift=0):
    output, textures = [], {}
    for e in elements:
        origin = [8+16*K*(e['center'][i]-center[i]+(y_shift if i==1 else 0)) for i in range(3)]
        cube = {'name':f"source_{e['piece']['file']}_{e['piece']['index']}_{e['element_index']}",
                'from':[round(origin[i]-8*K*e['size'][i],9) for i in range(3)],
                'to':[round(origin[i]+8*K*e['size'][i],9) for i in range(3)],
                'rotation':dict(zip(('x','y','z'),e['angles']),origin=[round(x,9) for x in origin]),
                'faces':{}, 'shade':e['shade']}
        if min(cube['from']) < -16 or max(cube['to']) > 32:
            raise ValueError(f'Out of model bounds: {cube["name"]}')
        for direction, face in e['faces'].items():
            name = face['texture'].split('/')[-1]
            textures[name] = 'barkan:block/piano/'+name
            cube['faces'][direction] = dict(face, texture='#'+name)
        output.append(cube)
    textures['particle'] = next(iter(textures.values()))
    model = {'format_version':'1.21.11','credit':'Original BarkanPiano geometry, lossless single-entity rebuild',
             'ambientocclusion':False,'textures':textures,'elements':output}
    if head is not None:
        model['display'] = {'head':head}
    return model


def verify(model, source, center, y_shift=0):
    worst = 0.
    if len(model['elements']) != len(source):
        raise ValueError('Element count mismatch')
    for cube, original in zip(model['elements'],source):
        rot = cube['rotation']; R = rotation(rot['x'],rot['y'],rot['z']); origin=rot['origin']
        for idx,(x,y,z) in enumerate(( (x,y,z) for x in (0,1) for y in (0,1) for z in (0,1) )):
            p=[cube['to' if bit else 'from'][i] for i,bit in enumerate((x,y,z))]
            v=mvec(R,[p[i]-origin[i] for i in range(3)])
            world=[(v[i]+origin[i]-8)/(16*K)+center[i] for i in range(3)]
            target=[n+(y_shift if i==1 else 0) for i,n in enumerate(original['source_vertices'][idx])]
            worst=max(worst,math.dist(world,target))
    if worst > VERTEX_TOLERANCE:
        raise ValueError(f'Geometry roundtrip error {worst} > {VERTEX_TOLERANCE}')
    return worst


def write_json(path, data, pretty=False):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2 if pretty else None,
                               separators=None if pretty else (',',':'))+'\n')


def bbmodel(model, vanilla, path):
    texture_names = [k for k in model['textures'] if k!='particle']
    textures=[]
    for i,name in enumerate(texture_names):
        raw=vanilla.z.read('assets/minecraft/textures/block/'+name+'.png')
        width,height=struct.unpack('>II',raw[16:24])
        textures.append({'path':'','name':name+'.png','folder':'block/piano','namespace':'barkan','id':str(i),
                         'width':width,'height':height,'uv_width':16,'uv_height':16,
                         'particle':i==0,'render_mode':'default','visible':True,'mode':'bitmap',
                         'uuid':str(uuid.uuid5(uuid.NAMESPACE_URL,'piano-texture:'+name)),
                         'source':'data:image/png;base64,'+base64.b64encode(raw).decode()})
    elements=[]
    for cube in model['elements']:
        item=copy.deepcopy(cube);r=item.pop('rotation');item['rotation']=[r['x'],r['y'],r['z']]
        item.update({'type':'cube','origin':r['origin'],'uuid':str(uuid.uuid5(uuid.NAMESPACE_URL,'piano:'+item['name'])),
                     'box_uv':False,'autouv':0,'locked':False,'visibility':True,'export':True})
        for face in item['faces'].values():face['texture']=texture_names.index(face['texture'][1:])
        elements.append(item)
    data={'meta':{'format_version':'4.10','model_format':'free','box_uv':False},'name':'Grand Piano — complete original geometry',
          'resolution':{'width':16,'height':16},'elements':elements,'textures':textures,
          'outliner':[e['uuid'] for e in elements]}
    write_json(path,data)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--jar',type=Path,default=DEFAULT_JAR);ap.add_argument('--client',type=Path,default=DEFAULT_CLIENT)
    ap.add_argument('--descriptor',type=Path,default=DEFAULT_DESC)
    ap.add_argument('--bbmodel',type=Path,default=Path('/tmp/piano-rebuild/full.bbmodel'))
    ap.add_argument('--head-transform',type=Path,help='JSON head display transform from verified renderer calibration')
    args=ap.parse_args()
    pieces,hashes=load_pieces(args.jar);vanilla=Vanilla(args.client);elements=source_elements(vanilla,pieces)
    if len(pieces)!=519 or len(elements)!=519:raise ValueError('Unexpected upstream geometry count')
    lo=[min(p[i] for e in elements for p in e['source_vertices']) for i in range(3)]
    hi=[max(p[i] for e in elements for p in e['source_vertices']) for i in range(3)]
    center=[round((lo[i]+hi[i])/2,9) for i in range(3)]
    head=json.loads(args.head_transform.read_text()) if args.head_transform else {
        'rotation':[0,0,0], 'scale':[round(1/(.625*K),9)]*3,
        'translation':[round(25.6*(center[i]-SEAT[k]-(1.6885 if i==1 else 0)),9) for i,k in enumerate(('x','y','z'))]}
    if any(abs(v)>80 for v in head['translation']) or any(abs(v)>4 for v in head['scale']):
        raise ValueError('Head transform exceeds vanilla translation/scale limits')
    full=make_model(elements,center,head);write_json(MODEL_DIR/'grand_full.json',full)
    worst=verify(json.loads((MODEL_DIR/'grand_full.json').read_text()),elements,center)
    write_json(ITEM_DIR/'grand_idle.json',{'model':{'type':'minecraft:model','model':'barkan:piano/grand_full'}})
    white=sorted([p for p in pieces if p['name']=='minecraft:quartz_block' and abs(p['m'][7]-1.0899)<.08],key=lambda p:p['m'][3])
    black=sorted([p for p in pieces if p['name']=='minecraft:polished_blackstone_slab' and abs(p['m'][7]-1.1384)<.08],key=lambda p:p['m'][3])
    white=white[-52:]
    if len(white)!=52 or len(black)!=36:raise ValueError('Upstream playable key count changed')
    wi=bi=0;keys=[];components=[{'type':'minecraft:model','model':'barkan:piano/single/body'}]
    active_ids={(p['file'],p['index']) for p in white+black}
    body=[e for e in elements if (e['piece']['file'],e['piece']['index']) not in active_ids]
    write_json(MODEL_DIR/'single/body.json',make_model(body,center,head))
    for midi in range(21,109):
        is_white=midi%12 in (0,2,4,5,7,9,11)
        p=white[wi] if is_white else black[bi]
        wi+=int(is_white);bi+=int(not is_white)
        selected=[e for e in elements if e['piece'] is p]
        flag=midi-21;name=f'key_{flag:02d}'
        for pressed in (False,True):
            suffix='down' if pressed else 'up';shift=(-.04 if is_white else -.008) if pressed else 0
            m=make_model(selected,center,head,shift);out=MODEL_DIR/f'single/{name}_{suffix}.json';write_json(out,m)
            worst=max(worst,verify(json.loads(out.read_text()),selected,center,shift))
        components.append({'type':'minecraft:condition','property':'minecraft:custom_model_data','index':flag,
                           'on_true':{'type':'minecraft:model','model':f'barkan:piano/single/{name}_down'},
                           'on_false':{'type':'minecraft:model','model':f'barkan:piano/single/{name}_up'}})
        keys.append({'flag':flag,'midi':midi,'file':p['file'],'index':p['index'],'color':'white' if is_white else 'black',
                     'pressed_y_offset':-.04 if is_white else -.008})
    write_json(ITEM_DIR/'grand_full.json',{'model':{'type':'minecraft:composite','models':components}})
    for name in full['textures']:
        if name=='particle':continue
        source='assets/minecraft/textures/block/'+name+'.png';TEX_DIR.mkdir(parents=True,exist_ok=True)
        (TEX_DIR/(name+'.png')).write_bytes(vanilla.z.read(source))
        if source+'.mcmeta' in vanilla.z.namelist():(TEX_DIR/(name+'.png.mcmeta')).write_bytes(vanilla.z.read(source+'.mcmeta'))
    matrix=[-1/K,0,0,center[0],0,1/K,0,center[1],0,0,-1/K,center[2],0,0,0,1]
    desc={'version':1,'item_model':'barkan:piano/grand_full','mcfunction_sha1':hashes,'seat':SEAT,'key_flags':88,
          'keys':keys,'model_scale':K,'model_center':center,'item_display_matrix':matrix,'head_transform':head,
          'expected':{'source_pieces':519,'model_elements':519,'fixed_elements':len(body),'playable_keys':88,'installed_entities':1},
          'validation':{'max_vertex_error_blocks':worst,'max_allowed_error_blocks':VERTEX_TOLERANCE,'bounds':[lo,hi]}}
    write_json(args.descriptor,desc,True);bbmodel(full,vanilla,args.bbmodel)
    # Exact allowlist: never scan-delete unrelated or future piano assets.
    removed=[]
    for folder in (MODEL_DIR,ITEM_DIR):
        for name in ('grand_axis',*(f'grand_r{i}' for i in range(1,6))):
            obsolete=folder/(name+'.json')
            if obsolete.exists():
                obsolete.unlink();removed.append(str(obsolete.relative_to(ROOT)))
    print(json.dumps({'descriptor':str(args.descriptor),'bbmodel':str(args.bbmodel),'elements':len(elements),'fixed':len(body),
                      'keys':len(keys),'max_vertex_error':worst,'center':center,'head_calibrated':head is not None,
                      'removed_obsolete_assets':removed},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
