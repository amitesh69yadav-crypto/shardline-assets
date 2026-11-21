"""
Shardfall Harbor — original SHARDLINE map, built in Blender (headless).

Run:  blender --background --factory-startup --python shardfall.py -- <out_dir> [preview]

Everything is authored in GAME space (x, y = up, z) — team 0 at -X, the map mirrored
across X = 0 — and rotated into Blender's Z-up frame at the end, so the glTF exporter's
+Y-up conversion lands back on game coordinates exactly.

Materials are named after the in-game surface they get (Poly Haven triplanar sets mapped by
MapDef.materialSurfaces); colour comes from per-vertex tint × height gradient (painted look).
Material names starting with "nc_" are visual only (no collision in game).
"""
import bpy, bmesh, math, random, sys, os
from mathutils import Matrix, Vector

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
OUT = argv[0] if argv else os.path.abspath('out')
PREVIEW = len(argv) > 1 and argv[1] == 'preview'
random.seed(7)

# ----------------------------------------------------------------- palette
def hexc(h, a=1.0):
    h = h.lstrip('#')
    return [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)] + [a]

PAL = {
    'cream': '#efe2c8', 'sand': '#e6c79a', 'terracotta': '#d8875c', 'rose': '#dba297', 'ochre': '#e4b45e',
    'teal': '#74b9ad', 'sky': '#9cc3d6', 'white': '#f4efe6', 'stone': '#c4b9a8', 'stoneDark': '#9f9586',
    'roof': '#c8623d', 'wood': '#8d5e3e', 'woodDark': '#6b442c', 'metal': '#7d8890', 'metalTeal': '#3f8f8a',
    'metalOrange': '#d9733a', 'glass': '#2c4a5c', 'fabricRed': '#c94b3f', 'fabricCream': '#f1e6cf',
    'fabricTeal': '#3aa39a', 'leaf': '#6f9a4a', 'leafDark': '#4f7a3a', 'cobble': '#bfb2a0', 'concrete': '#b8b3aa',
    'seabed': '#cdb88f', 'crystal': '#5fe6d6', 'glow': '#2fffe0', 'boatBlue': '#3d7fa6', 'boatRed': '#b9473a',
}
P = {k: hexc(v) for k, v in PAL.items()}
BUILD_TINTS = ['cream', 'sand', 'terracotta', 'rose', 'ochre', 'teal', 'white']

# ----------------------------------------------------------------- mesh builder
class MB:
    """Per-material bmesh accumulator with a corner colour layer."""
    def __init__(self):
        self.bms = {}

    def bm(self, mat):
        if mat not in self.bms:
            b = bmesh.new()
            b.loops.layers.color.new('Col')
            self.bms[mat] = b
        return self.bms[mat]

MBX = MB()

def smooth(e0, e1, x):
    t = max(0.0, min(1.0, (x - e0) / (e1 - e0)))
    return t * t * (3 - 2 * t)

def paint(bm, faces, tint, mode='world', y0=0.0, h=1.0, jitter=0.035):
    """Tint × height gradient: darker at the foot of walls, lighter toward the top (hand-painted look)."""
    col = bm.loops.layers.color['Col']
    j = 1.0 + random.uniform(-jitter, jitter)
    for f in faces:
        for l in f.loops:
            y = l.vert.co.y
            if mode == 'world':
                g = 0.74 + 0.26 * smooth(-0.5, 3.2, y)
            elif mode == 'local':
                g = 0.82 + 0.18 * smooth(y0, y0 + h, y)
            else:
                g = 1.0
            # Faces pointing down are in shadow-ish; tops catch light.
            n = f.normal
            g *= 0.9 if n.y < -0.5 else (1.04 if n.y > 0.5 else 1.0)
            l[col] = (min(1, tint[0] * g * j), min(1, tint[1] * g * j), min(1, tint[2] * g * j), 1.0)

def merge_into(dst, src):
    """Append src bmesh geometry (with corner colours) to dst; returns the new faces."""
    cs, cd = src.loops.layers.color['Col'], dst.loops.layers.color['Col']
    vm = {v: dst.verts.new(v.co) for v in src.verts}
    out = []
    for f in src.faces:
        nf = dst.faces.new([vm[v] for v in f.verts])
        for la, lb in zip(f.loops, nf.loops):
            lb[cd] = la[cs]
        out.append(nf)
    return out

def box(cx, y0, cz, w, h, d, mat, tint, bevel=0.0, seg=1, yaw=0.0, mode='world'):
    """Axis box (w along x, h up, d along z) rotated by yaw (deg) about its centre."""
    if bevel > 0 and min(w, h, d) > bevel * 2.5:
        # Bevel in a scratch mesh (bevel replaces faces), paint, then append.
        tmp = bmesh.new()
        tmp.loops.layers.color.new('Col')
        MBX.bms['__tmp'] = tmp
        box(cx, y0, cz, w, h, d, '__tmp', tint, 0.0, seg, yaw, mode)
        del MBX.bms['__tmp']
        bmesh.ops.bevel(tmp, geom=list(tmp.edges), offset=bevel, offset_type='OFFSET', segments=seg, profile=0.5, affect='EDGES', clamp_overlap=True)
        tmp.normal_update()
        paint(tmp, list(tmp.faces), tint, mode, y0, h)
        faces = merge_into(MBX.bm(mat), tmp)
        tmp.free()
        return faces
    bm = MBX.bm(mat)
    hw, hd = w / 2, d / 2
    c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    pts = []
    for (lx, ly, lz) in [(-hw, 0, -hd), (hw, 0, -hd), (hw, 0, hd), (-hw, 0, hd), (-hw, h, -hd), (hw, h, -hd), (hw, h, hd), (-hw, h, hd)]:
        x = lx * c + lz * s
        z = -lx * s + lz * c
        pts.append(bm.verts.new((cx + x, y0 + ly, cz + z)))
    idx = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    faces = [bm.faces.new([pts[i] for i in f]) for f in idx]
    for f in faces:
        f.normal_update()
    paint(bm, faces, tint, mode, y0, h)
    return faces

def prism(points, z0, z1, mat, tint, plane='xy', mode='world'):
    """Extrude a 2D outline. plane 'xy': points are (x, y) cross-section extruded along z (z0..z1).
    plane 'xz': points are (x, z) plan extruded along y (z0..z1 are heights)."""
    bm = MBX.bm(mat)
    def P3(a, b, t):
        return (a, b, t) if plane == 'xy' else (a, t, b)
    lo = [bm.verts.new(P3(a, b, z0)) for (a, b) in points]
    hi = [bm.verts.new(P3(a, b, z1)) for (a, b) in points]
    faces = []
    faces.append(bm.faces.new(list(reversed(lo)) if plane == 'xy' else lo))
    faces.append(bm.faces.new(hi if plane == 'xy' else list(reversed(hi))))
    n = len(points)
    for i in range(n):
        j = (i + 1) % n
        q = [lo[i], lo[j], hi[j], hi[i]] if plane == 'xy' else [lo[i], hi[i], hi[j], lo[j]]
        faces.append(bm.faces.new(q))
    bm.normal_update()
    for f in faces:
        f.normal_update()
    # Fix winding if the outline was clockwise (normals pointing inward).
    cen = Vector((0, 0, 0))
    for v in lo + hi:
        cen += v.co
    cen /= len(lo + hi)
    if (faces[2].calc_center_median() - cen).dot(faces[2].normal) < 0:
        bmesh.ops.reverse_faces(bm, faces=faces)
        bm.normal_update()
    paint(bm, faces, tint, mode)
    return faces

def cyl(cx, y0, cz, r, h, mat, tint, segs=12, r2=None, mode='world'):
    bm = MBX.bm(mat)
    m = Matrix.Translation((cx, y0 + h / 2, cz)) @ Matrix.Rotation(math.radians(-90), 4, 'X')
    res = bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segs, radius1=r, radius2=(r if r2 is None else r2), depth=h, matrix=m)
    faces = list({f for v in res['verts'] for f in v.link_faces})
    bm.normal_update()
    paint(bm, faces, tint, mode, y0, h)
    return faces

def blob(cx, cy, cz, sx, sy, sz, mat, tint, subdiv=1, seed=0, mode='local'):
    """Irregular rock / foliage lump: a jittered icosphere."""
    bm = MBX.bm(mat)
    rnd = random.Random(seed)
    m = Matrix.Translation((cx, cy, cz)) @ Matrix.Diagonal((sx, sy, sz, 1))
    res = bmesh.ops.create_icosphere(bm, subdivisions=subdiv, radius=1.0, matrix=m)
    for v in res['verts']:
        v.co.x += rnd.uniform(-0.12, 0.12) * sx
        v.co.y += rnd.uniform(-0.12, 0.12) * sy
        v.co.z += rnd.uniform(-0.12, 0.12) * sz
    faces = list({f for v in res['verts'] for f in v.link_faces})
    bm.normal_update()
    paint(bm, faces, tint, mode, cy - sy, sy * 2)
    return faces

def mirror_x(fn):
    """Author on the -X half; also emit the +X mirror (team 1 side)."""
    def run(*a, **k):
        fn(1, *a, **k)
        fn(-1, *a, **k)
    return run

# ----------------------------------------------------------------- architecture kit
FLOOR_H = 3.4

def window(x, y, z, nx, nz, tint_shutter):
    """Window on a wall whose outward normal is (nx, nz): glass, frame, sill, open shutters."""
    yaw = math.degrees(math.atan2(nx, nz))
    ox, oz = nx * 0.06, nz * 0.06
    box(x + ox, y, z + oz, 1.1, 1.6, 0.06, 'glass', P['glass'], yaw=yaw, mode='flat')
    box(x + nx * 0.02, y - 0.12, z + nz * 0.02, 1.38, 1.86, 0.08, 'wood', P['woodDark'], yaw=yaw, mode='flat')
    box(x + nx * 0.14, y - 0.2, z + nz * 0.14, 1.5, 0.12, 0.3, 'stone', P['stone'], yaw=yaw, mode='flat')
    rx, rz = nz, -nx  # wall tangent
    for sgn in (-1, 1):
        box(x + rx * sgn * 1.02 + nx * 0.08, y, z + rz * sgn * 1.02 + nz * 0.08, 0.5, 1.6, 0.06, 'wood', tint_shutter, yaw=yaw, mode='local')

def door(x, z, nx, nz, tint):
    yaw = math.degrees(math.atan2(nx, nz))
    box(x + nx * 0.05, 0, z + nz * 0.05, 1.5, 2.5, 0.08, 'wood', tint, yaw=yaw, mode='local')
    box(x + nx * 0.02, 0, z + nz * 0.02, 2.0, 2.85, 0.1, 'stone', P['stone'], yaw=yaw, mode='flat')

def awning(x, y, z, nx, nz, width, colors):
    """Striped shop awning sloping out from a wall."""
    yaw = math.degrees(math.atan2(nx, nz))
    strips = max(3, int(width / 0.6))
    rx, rz = nz, -nx
    verts = set()
    for i in range(strips):
        t = (i + 0.5) / strips - 0.5
        cx = x + rx * t * width + nx * 0.8
        cz = z + rz * t * width + nz * 0.8
        f = box(cx, y, cz, width / strips + 0.01, 0.06, 1.7, 'fabric', colors[i % 2], yaw=yaw, mode='flat')
        verts |= {v for face in f for v in face.verts}
    # Slope: tilt the strips by moving their outer edge down (shear the just-built verts).
    for v in verts:
        out = (v.co.x - x) * nx + (v.co.z - z) * nz
        v.co.y -= max(0.0, out - 0.1) * 0.45

def building(x0, x1, z0, z1, floors, tint, roof='flat', windows=True, doors=True, shutter='teal', skip_sides=(), gap=None):
    """gap = (side 'e'/'w', z_from, z_to): opening in the roof parapet where a stair arrives."""
    """Plastered block with stone plinth, floor cornices, windows, parapet or tiled gable roof."""
    H = floors * FLOOR_H
    w, d = x1 - x0, z1 - z0
    cx, cz = (x0 + x1) / 2, (z0 + z1) / 2
    box(cx, 0, cz, w, H, d, 'plaster', P[tint], bevel=0.12, seg=2)
    box(cx, -0.3, cz, w + 0.24, 1.2, d + 0.24, 'stone', P['stoneDark'], bevel=0.05)
    for f in range(1, floors):
        box(cx, f * FLOOR_H - 0.15, cz, w + 0.3, 0.3, d + 0.3, 'plaster', P['white'], bevel=0.05, mode='flat')
    if roof == 'flat':
        box(cx, H - 0.05, cz, w + 0.5, 0.35, d + 0.5, 'stone', P['stone'], bevel=0.05, mode='flat')
        t = 0.45
        segs = [(cx, z0 + t / 2, w, t), (cx, z1 - t / 2, w, t)]
        for (side, xe) in (('w', x0 + t / 2), ('e', x1 - t / 2)):
            if gap and gap[0] == side:
                ga, gb = sorted(gap[1:])
                for (a, b) in ((z0, ga), (gb, z1)):
                    if b - a > 0.3:
                        segs.append((xe, (a + b) / 2, t, b - a))
            else:
                segs.append((xe, cz, t, d))
        for (px, pz, pw, pd) in segs:
            box(px, H + 0.3, pz, pw, 0.9, pd, 'plaster', P[tint], bevel=0.06)
    else:
        ridge_along_x = w >= d
        span = d if ridge_along_x else w
        rise = min(3.2, span * 0.32)
        o = 0.6
        if ridge_along_x:
            pts = [(z0 - o, H - 0.1), (z1 + o, H - 0.1), (cz, H + rise)]
            faces = prism([(p[0], p[1]) for p in pts], 0, 1, 'roof', P['roof'], plane='xy')
            # prism() extrudes along z; rebuild along x by swapping axes of the just-built verts.
            for v in {v for f in faces for v in f.verts}:
                zz, yy, t = v.co.x, v.co.y, v.co.z
                v.co.x = x0 - o + t * (w + 2 * o)
                v.co.z = zz
            box(cx, H + rise - 0.12, cz, w + 2 * o, 0.3, 0.4, 'roof', P['roof'], mode='flat')
        else:
            pts = [(x0 - o, H - 0.1), (x1 + o, H - 0.1), (cx, H + rise)]
            prism(pts, z0 - o, z1 + o, 'roof', P['roof'], plane='xy')
            box(cx, H + rise - 0.12, cz, 0.4, 0.3, d + 2 * o, 'roof', P['roof'], mode='flat')
        bm = MBX.bm('roof')
        bm.normal_update()
        # Chimney
        box(x0 + w * 0.3, H, z0 + d * 0.4, 0.9, rise + 1.4, 0.9, 'plaster', P['white'], bevel=0.05)
    if not windows:
        return
    sides = [('n', 0, 1), ('s', 0, -1), ('e', 1, 0), ('w', -1, 0)]
    for (name, nx, nz) in sides:
        if name in skip_sides:
            continue
        length = w if nz else d
        n = int((length - 1.5) // 3.2)
        if n <= 0:
            continue
        for i in range(n):
            t = (i + 0.5) / n - 0.5
            px = cx + t * (length - 1.5) if nz else (x1 if nx > 0 else x0)
            pz = cz + t * (length - 1.5) if nx else (z1 if nz > 0 else z0)
            for f in range(floors):
                if f == 0 and doors and i % 3 == 1:
                    door(px, pz, nx, nz, P['woodDark'] if i % 2 else P[shutter])
                    continue
                window(px, f * FLOOR_H + 1.0, pz, nx, nz, P[shutter])

def stairs(x0, z0, x1, z1, y0, y1, axis, mat='stone', tint=None, width_side=None):
    """Straight stair filling the rect, rising along +axis ('x', '-x', 'z', '-z') from y0 to y1, 0.25 m risers."""
    tint = tint or P['stone']
    rise = y1 - y0
    n = max(1, int(round(rise / 0.25)))
    for i in range(n):
        t0 = i / n
        h = y0 + (i + 1) * rise / n
        if axis in ('x', '-x'):
            run = x1 - x0
            a = x0 + run * t0 if axis == 'x' else x1 - run * (t0 + 1 / n)
            box(a + run / n / 2, y0 - 0.2, (z0 + z1) / 2, run / n, h - y0 + 0.2, z1 - z0, mat, tint, mode='flat')
        else:
            run = z1 - z0
            a = z0 + run * t0 if axis == 'z' else z1 - run * (t0 + 1 / n)
            box((x0 + x1) / 2, y0 - 0.2, a + run / n / 2, x1 - x0, h - y0 + 0.2, run / n, mat, tint, mode='flat')

def railing(xa, za, xb, zb, y, h=1.0):
    L = math.hypot(xb - xa, zb - za)
    yaw = math.degrees(math.atan2(xb - xa, zb - za))
    n = max(2, int(L / 1.2) + 1)
    for i in range(n):
        t = i / (n - 1)
        cyl(xa + (xb - xa) * t, y, za + (zb - za) * t, 0.05, h, 'metal', P['metal'], segs=6)
    box((xa + xb) / 2, y + h - 0.06, (za + zb) / 2, 0.08, 0.08, L, 'metal', P['metalTeal'], yaw=yaw, mode='flat')

def arch_span(x0, x1, z, y_spring, y_top, depth, tint):
    """Arched opening spandrel between two pillars (semicircle under a flat top), along x at depth z."""
    r = (x1 - x0) / 2
    cx = (x0 + x1) / 2
    pts = [(x0, y_top), (x0, y_spring)]
    for i in range(1, 12):
        a = math.pi - i / 12 * math.pi
        pts.append((cx + math.cos(a) * r, y_spring + math.sin(a) * r))
    pts += [(x1, y_spring), (x1, y_top)]
    prism(pts, z - depth / 2, z + depth / 2, 'plaster', P[tint], plane='xy')

def crate(x, y, z, s, yaw=0, tint=None):
    box(x, y, z, s, s, s, 'wood', tint or P['wood'], bevel=0.04, yaw=yaw, mode='local')
    box(x, y + s * 0.42, z, s + 0.04, s * 0.16, s + 0.04, 'wood', P['woodDark'], yaw=yaw, mode='flat')

def barrel(x, y, z, tint=None):
    cyl(x, y, z, 0.42, 1.1, 'wood', tint or P['wood'], segs=10, mode='local')
    cyl(x, y + 0.25, z, 0.44, 0.08, 'metal', P['metal'], segs=10)
    cyl(x, y + 0.8, z, 0.44, 0.08, 'metal', P['metal'], segs=10)

def lamp(x, z, h=4.2):
    cyl(x, 0, z, 0.12, h, 'metal', P['metalTeal'], segs=8)
    cyl(x, 0, z, 0.25, 0.5, 'stone', P['stone'], segs=8)
    box(x, h, z, 0.5, 0.6, 0.5, 'metal', P['metalTeal'], mode='flat')
    box(x, h + 0.08, z, 0.38, 0.44, 0.38, 'glow', P['glow'], mode='flat')
    cyl(x, h + 0.6, z, 0.36, 0.25, 'metal', P['metalTeal'], segs=8, r2=0.08)

def tree(x, y, z, s=1.0, seed=0):
    cyl(x, y, z, 0.18 * s, 2.6 * s, 'wood', P['woodDark'], segs=8)
    rnd = random.Random(seed)
    for i in range(4):
        blob(x + rnd.uniform(-0.8, 0.8) * s, y + (2.8 + rnd.uniform(0, 1.2)) * s, z + rnd.uniform(-0.8, 0.8) * s,
             1.3 * s, 1.0 * s, 1.3 * s, 'nc_leaves', P['leaf'] if i % 2 else P['leafDark'], seed=seed * 10 + i)

def planter(x, z, w=2.2, d=1.2, with_tree=True, seed=0):
    box(x, 0, z, w, 0.8, d, 'stone', P['stone'], bevel=0.06)
    box(x, 0.8, z, w - 0.2, 0.08, d - 0.2, 'stone', P['seabed'], mode='flat')
    if with_tree:
        tree(x, 0.85, z, 0.9, seed)
    else:
        for i in range(5):
            blob(x - w / 2 + 0.3 + i * (w - 0.6) / 4, 1.0, z, 0.3, 0.25, 0.3, 'nc_leaves', P['leaf'], subdiv=1, seed=seed + i)

def stall(x, z, yaw, colors):
    c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    box(x, 0, z, 2.6, 0.95, 1.2, 'wood', P['wood'], bevel=0.04, yaw=yaw, mode='local')
    for (lx, lz) in [(-1.2, -0.5), (1.2, -0.5), (-1.2, 0.5), (1.2, 0.5)]:
        cyl(x + lx * c + lz * s, 0, z - lx * s + lz * c, 0.05, 2.3, 'wood', P['woodDark'], segs=6)
    for i in range(6):
        t = (i + 0.5) / 6 - 0.5
        box(x + t * 2.9 * c, 2.3, z - t * 2.9 * s, 2.9 / 6 + 0.01, 0.05, 1.7, 'fabric', colors[i % 2], yaw=yaw, mode='flat')
    for i in range(3):
        crate(x + (i - 1) * 0.7 * c, 0.95, z - (i - 1) * 0.7 * s, 0.45, yaw, P['ochre'] if i == 1 else P['wood'])

def container(x, z, yaw, tint):
    box(x, 0, z, 6.0, 2.6, 2.45, 'metal', tint, bevel=0.06, yaw=yaw, mode='local')
    c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    for i in range(9):
        t = (i / 8 - 0.5) * 5.6
        box(x + t * c, 0.1, z - t * s, 0.1, 2.4, 2.55, 'metal', [k * 0.85 for k in tint[:3]] + [1], yaw=yaw, mode='flat')

def boat(x, z, length, tint, yaw=0):
    """Moored fishing boat: tapered hull (walkable deck) with a little cabin."""
    hl, hw = length / 2, length * 0.17
    plan = [(-hl, -hw), (hl * 0.55, -hw), (hl, 0), (hl * 0.55, hw), (-hl, hw)]
    c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    pts = [(x + a * c + b * s, z - a * s + b * c) for (a, b) in plan]
    prism(pts, -0.9, 0.35, 'wood', tint, plane='xz', mode='local')
    inner = [(x + a * 0.9 * c + b * 0.85 * s, z - a * 0.9 * s + b * 0.85 * c) for (a, b) in plan]
    prism(inner, 0.35, 0.42, 'wood', P['wood'], plane='xz', mode='flat')
    box(x - hl * 0.25 * c, 0.42, z + hl * 0.25 * s, length * 0.28, 1.5, hw * 1.3, 'plaster', P['white'], bevel=0.05, yaw=yaw)
    box(x - hl * 0.25 * c, 1.92, z + hl * 0.25 * s, length * 0.32, 0.12, hw * 1.5, 'wood', P['woodDark'], yaw=yaw, mode='flat')

def rock(x, y, z, s, seed):
    blob(x, y, z, s * random.Random(seed).uniform(0.9, 1.4), s * 0.75, s, 'stone', P['stoneDark'], subdiv=1, seed=seed)

# ----------------------------------------------------------------- the map
def ground():
    # Streets, plaza, spawn courtyards: cobble (both halves in one go).
    box(0, -0.5, 29, 144, 0.5, 10, 'cobble', P['cobble'])                        # north lane (incl. spawns)
    box(0, -0.5, 35.6, 144, 0.5, 3.3, 'stone', P['stone'])                       # arcade walkway floor
    box(0, -0.5, 0, 60, 0.5, 24, 'cobble', P['cobble'])                          # plaza
    for sx in (-1, 1):
        box(sx * 65, -0.5, 6, 14, 0.5, 56, 'cobble', P['cobble'])               # spawn courtyard x∈[58,72]
        box(sx * 44, -0.5, 0, 28, 0.5, 10, 'cobble', P['cobble'])               # approach + gate passage
        box(sx * 36, -0.5, 18, 4, 0.5, 12, 'cobble', P['cobble'])               # north alley
        box(sx * 36, -0.5, -17, 4, 0.5, 10, 'cobble', P['cobble'])              # south alley
    box(0, -0.5, -17, 12, 0.5, 10, 'cobble', P['cobble'])                        # central passage to the quay
    box(0, -0.5, -26, 148, 0.5, 8, 'concrete', P['concrete'])                    # quay
    box(0, -1.4, -30.3, 148, 1.4, 0.6, 'stone', P['stoneDark'], bevel=0.05)     # quay wall
    box(0, -1.7, -41, 152, 0.5, 22, 'nc_seabed' if False else 'sand', P['seabed'])  # sea bed (walkable, knee deep)
    MBX.bm('nc_water')
    box(0, -0.48, -44, 190, 0.02, 34, 'nc_water', hexc('#3aa0a8'), mode='flat')  # water surface (visual only)

@mirror_x
def half(sx):
    X = lambda v: sx * v  # mirror helper for x coordinates
    def xr(a, b):  # mirrored x-range → (lo, hi)
        a, b = X(a), X(b)
        return (min(a, b), max(a, b))

    # --- North row (boundary) with arcade over the market street: z∈[34,48]
    segs = [(-72, -56, 'ochre', 'gable'), (-56, -42, 'cream', 'flat'), (-42, -26, 'terracotta', 'gable'), (-26, -12, 'rose', 'flat'), (-12, 0, 'sand', 'gable')]
    for (a, b, tint, roof) in segs:
        x0, x1 = xr(a, b)
        floors = 3 if roof == 'gable' else 2
        building(x0, x1, 37, 48, floors, tint, roof=roof, skip_sides=('n',), shutter='teal' if tint != 'teal' else 'terracotta')
        # Upper floors overhang the arcade walkway z∈[34,37].
        H = floors * FLOOR_H
        box((x0 + x1) / 2, 4.2, 35.5, x1 - x0, H - 4.2, 3.0, 'plaster', P[tint], bevel=0.1)
        for f in range(2, floors + 1):
            if f * FLOOR_H > 4.2:
                pass
        n = int((x1 - x0) // 4)
        for i in range(n + 1):
            px = x0 + i * (x1 - x0) / n
            box(px, 0, 34.45, 0.8, 4.2, 0.8, 'stone', P['stone'], bevel=0.08)
            if i < n:
                arch_span(px + 0.4, x0 + (i + 1) * (x1 - x0) / n - 0.4, 34.45, 2.4, 4.2, 0.6, tint)
        for i in range(n):
            px = x0 + (i + 0.5) * (x1 - x0) / n
            window(px, 5.2, 34.0, 0, -1, P['teal'] if tint != 'teal' else P['terracotta'])
            if floors > 2:
                window(px, 8.6, 34.0, 0, -1, P['teal'])
        # balcony rail on top of the arcade front
        lamp(X(-48), 32.6) if a == -56 else None

    # --- Block row between the market street and the plaza: z∈[12,24]
    outer = 'w' if sx > 0 else 'e'  # sx = +1 is the -X half: its courtyard is to the west
    building(*xr(-58, -38), 12, 24, 2, 'teal', roof='flat', shutter='terracotta', gap=(outer, 20.6, 23.6), skip_sides=(outer,))
    ax0, ax1 = xr(-60.4, -58)
    stairs(ax0, 13, ax1, 23, 0, 6.8, 'z', 'stone')                               # roof access from the spawn courtyard
    railing(X(-36.4), 13, X(-36.4), 23, 0.0, 1.0) if False else None
    building(*xr(-34, -12), 12, 24, 3, 'terracotta', roof='gable', shutter='teal')
    # Customs house (centre, spans the mirror axis): archway passage x∈[-4,4]
    if sx < 0:
        H = 2 * FLOOR_H + 1.0
        for (a, b) in [(-12, -4), (4, 12)]:
            building(a, b, 12, 24, 2, 'white', roof='flat', shutter='teal', skip_sides=('e',) if a < 0 else ('w',))
        box(0, 4.6, 18, 8, H - 4.6, 12, 'plaster', P['white'], bevel=0.1)        # bridge over the passage
        arch_span(-4, 4, 12.2, 2.6, 4.6, 0.5, 'white')
        arch_span(-4, 4, 23.8, 2.6, 4.6, 0.5, 'white')
        cyl(0, H, 18, 3.2, 3.2, 'plaster', P['white'], segs=16)                 # drum
        cyl(0, H + 3.2, 18, 3.4, 0.4, 'stone', P['stone'], segs=16)
        cyl(0, H + 3.6, 18, 3.2, 2.6, 'roof', P['metalTeal'], segs=16, r2=0.4)  # teal dome
        cyl(0, H + 6.2, 18, 0.3, 1.6, 'glow', P['glow'], segs=8)
        for i in range(8):
            a = i / 8 * math.tau
            window(math.cos(a) * 3.25, H + 1.0, 18 + math.sin(a) * 3.25, math.cos(a), math.sin(a), P['teal'])

    # --- Approach & gate: z∈[-12,12], x∈[-58,-30]
    building(*xr(-58, -44), 5, 12, 2, 'sand', roof='flat')
    building(*xr(-58, -44), -12, -5, 2, 'rose', roof='flat')
    building(*xr(-44, -30), 5, 12, 2, 'cream', roof='flat', skip_sides=())
    building(*xr(-44, -30), -12, -5, 2, 'cream', roof='flat')
    gx0, gx1 = xr(-44, -30)
    box((gx0 + gx1) / 2, 4.5, 0, gx1 - gx0, 2.3, 10, 'plaster', P['cream'], bevel=0.1)   # bridge over the gate passage
    box((gx0 + gx1) / 2, 4.35, 0, gx1 - gx0 + 0.3, 0.3, 10.3, 'stone', P['stone'], mode='flat')
    for zz in (-2.6, 0, 2.6):
        window(gx0, 5.0, zz, -1, 0, P['teal'])
        window(gx1, 5.0, zz, 1, 0, P['teal'])
    for zz in (-5, 5):
        pass
    arch_span(gx0, gx1, -4.8, 3.0, 4.5, 0.4, 'cream') if False else None
    # Gate archway faces
    for (ax, depth) in [(X(-30.2), 0.4), (X(-43.8), 0.4)]:
        pass

    # --- Plaza terraces: x∈[-30,-22], z∈±[5,12], y = 2.5
    for zc in (8.5, -8.5):
        tx0, tx1 = xr(-30, -22)
        box((tx0 + tx1) / 2, 0, zc, tx1 - tx0, 2.5, 7, 'stone', P['stone'], bevel=0.08)
        box((tx0 + tx1) / 2, 2.5, zc, tx1 - tx0, 0.05, 7, 'tiles', P['white'], mode='flat')
        sx0, sx1 = xr(-22, -18.25)
        stairs(sx0, zc - 2.5, sx1, zc + 2.5, 0, 2.5, '-x' if sx > 0 else 'x')
        # balustrade along the plaza edge except the stairs and along the passage side
        edge_z = 5.0 if zc > 0 else -5.0
        box((tx0 + tx1) / 2, 2.5, edge_z + (0.2 if zc > 0 else -0.2), tx1 - tx0, 1.0, 0.4, 'stone', P['stone'], bevel=0.05)
        planter(X(-27.5), zc + (2.2 if zc > 0 else -2.2), 1.8, 1.8, True, seed=int(zc * 10) + (3 if sx > 0 else 0))
        planter(X(-27.5), zc + (2.2 if zc > 0 else -2.2), 1.8, 1.8, False) if False else None

    # --- South block row: z∈[-22,-12]
    building(*xr(-58, -38), -22, -12, 2, 'ochre', roof='flat', shutter='teal', gap=(outer, -21.6, -18.6), skip_sides=(outer,))
    ax0, ax1 = xr(-60.4, -58)
    stairs(ax0, -21, ax1, -13, 0, 6.8, '-z', 'stone')                            # roof access from the spawn courtyard
    building(*xr(-34, -6), -22, -12, 2, 'sand', roof='gable', shutter='teal', skip_sides=())
    # Shop awnings on the quay side
    for i in range(4):
        px = X(-31 + i * 6.5)
        awning(px, 3.0, -22.0, 0, -1, 4.2, [P['fabricTeal'], P['fabricCream']] if i % 2 else [P['fabricRed'], P['fabricCream']])
    for i in range(3):
        px = X(-55 + i * 6)
        awning(px, 3.0, -22.0, 0, -1, 4.0, [P['fabricRed'], P['fabricCream']])

    # --- Market street props (cover), mirrored
    stall(X(-48), 31.5, 0, [P['fabricRed'], P['fabricCream']])
    stall(X(-20), 26.5, 180, [P['fabricTeal'], P['fabricCream']])
    stall(X(-8), 31.5, 0, [P['fabricCream'], P['fabricRed']])
    for (px, pz) in [(-40, 26.2), (-41, 26.9), (-28, 32.4)]:
        crate(X(px), 0, pz, 1.0, yaw=random.uniform(-15, 15))
    barrel(X(-33), 0, 26.0)
    barrel(X(-32.2), 0, 26.4)
    planter(X(-54), 25.4, 2.4, 1.2, False, seed=11)
    lamp(X(-26), 24.6)
    lamp(X(-50), 24.6)

    # --- Spawn courtyard: x∈[-72,-58]
    sx0, sx1 = xr(-73.5, -72)
    box((sx0 + sx1) / 2, 0, 9, 1.5, 7, 78, 'stone', P['stoneDark'], bevel=0.1)   # back wall
    for i in range(13):
        box(X(-72.75), 7, -29 + i * 6, 1.5, 0.9, 2.4, 'stone', P['stoneDark'], bevel=0.06)
    planter(X(-66), 14, 3.0, 3.0, True, seed=21 + (5 if sx > 0 else 0))
    planter(X(-66), -14, 3.0, 3.0, True, seed=31 + (5 if sx > 0 else 0))
    crate(X(-61), 9.5, 0, 1.2) if False else None
    crate(X(-61), 0, 9.5, 1.2, 10)
    crate(X(-61), 0, -9.5, 1.2, -12)
    crate(X(-61), 1.2, -9.5, 0.9, 30)
    lamp(X(-70.5), 22)
    lamp(X(-70.5), -10)

    # --- Quay props
    container(X(-50), -25.0, 0, P['metalTeal'] if sx < 0 else P['metalOrange'])
    container(X(-50), -27.6, 0, P['metalOrange'] if sx < 0 else P['metalTeal'])
    for (px, pz, s) in [(-40, -24.5, 1.1), (-39, -25.6, 1.0), (-39.6, -24.9, 0.9)]:
        crate(X(px), 0 if s > 0.95 else 1.1, pz, s, yaw=random.uniform(-20, 20))
    barrel(X(-26), 0, -28.8)
    barrel(X(-25.2), 0, -29.2)
    for i in range(6):                                                         # bollards
        cyl(X(-66 + i * 10), 0, -29.5, 0.25, 0.7, 'metal', P['metal'], segs=8, r2=0.3)
    # Steps down to the water so waders can climb back out.
    stx0, stx1 = xr(-31, -28)
    stairs(stx0, -33.2, stx1, -30.6, -1.2, 0.0, 'z')

    # --- Piers and boats
    for (pxa, length) in [(-44, 15), (-20, 13)]:
        p0, p1 = xr(pxa - 1.5, pxa + 1.5)
        box((p0 + p1) / 2, -0.25, -30.6 - length / 2, 3, 0.3, length, 'wood', P['wood'], mode='flat')
        for k in range(int(length // 3) + 1):
            for side in (-1.3, 1.3):
                cyl(X(pxa) + side, -1.6, -31 - k * 3, 0.16, 2.0, 'wood', P['woodDark'], segs=6)
        boat(X(pxa + 4.2), -36.5 - length * 0.2, 7.5, P['boatBlue'] if sx < 0 else P['boatRed'], yaw=90)
    # Harbour crane on the quay
    cx = X(-10)
    for dz in (-23.0, -29.0):
        for dx in (-1.5, 1.5):
            box(cx + dx, 0, dz, 0.5, 9, 0.5, 'metal', P['metalOrange'], bevel=0.04)
    box(cx, 9, -26, 3.5, 0.8, 7, 'metal', P['metalOrange'], bevel=0.05)
    box(cx + X(1) * 3.5, 9.8, -26, 9, 0.6, 0.6, 'metal', P['metalOrange'], bevel=0.04)
    box(cx, 9.8, -26, 2.4, 2.0, 2.4, 'metal', P['metalTeal'], bevel=0.06)

    # --- Breakwater rocks (south boundary)
    for i in range(10):
        rock(X(-4 - i * 7.2), -0.8, -52 + random.Random(i).uniform(-1, 1), 3.4, seed=i * 3 + (100 if sx > 0 else 0))

def centre():
    # Shard Plaza: basin ring + the crashed crystal.
    ring = []
    for i in range(20):
        a = i / 20 * math.tau
        x, z = math.cos(a) * 7.2, math.sin(a) * 7.2
        box(x, 0, z, 2.4, 0.95, 0.9, 'stone', P['stone'], bevel=0.08, yaw=math.degrees(-a) + 90)
    cyl(0, -0.02, 0, 6.8, 0.08, 'tiles', P['sky'], segs=24)
    for (dx, dz, h, tilt, r) in [(0, 0, 9.0, 0, 1.5), (1.6, 0.8, 6.0, 18, 0.9), (-1.4, 1.2, 5.0, -22, 0.8), (0.6, -1.6, 4.2, 25, 0.7), (-0.9, -1.1, 3.4, -15, 0.6)]:
        faces = cyl(dx, 0, dz, r, h, 'crystal', P['crystal'], segs=6, r2=0.05)
        bm = MBX.bm('crystal')
        # Tilt each spike away from the centre.
        ax = Vector((dz, 0, -dx)).normalized() if (dx or dz) else Vector((1, 0, 0))
        rot = Matrix.Rotation(math.radians(tilt), 3, ax)
        verts = list({v for f in faces for v in f.verts})
        for v in verts:
            v.co = Vector((dx, 0, dz)) + rot @ (v.co - Vector((dx, 0, dz)))
        cyl(dx, h * 0.15, dz, r * 0.35, h * 0.6, 'glow', P['glow'], segs=6, r2=0.02)
    # Debris chunks thrown out by the impact
    for i in range(9):
        a = i / 9 * math.tau + 0.3
        rock(math.cos(a) * 4.4, 0.1, math.sin(a) * 4.4, 0.6 + (i % 3) * 0.2, seed=200 + i)
    # Benches + lamps around the plaza
    for (x, z) in [(-14, 10.6), (14, 10.6), (-14, -10.6), (14, -10.6)]:
        box(x, 0, z, 2.6, 0.45, 0.7, 'wood', P['wood'], bevel=0.04, mode='local')
        box(x, 0, z, 2.4, 0.25, 0.5, 'stone', P['stone'], mode='flat')
    for (x, z) in [(-12, 0), (12, 0)]:
        lamp(x, z + 6.5)
        lamp(x, z - 6.5)
    # Lighthouse island on the centre pier
    box(0, -0.25, -36, 3.6, 0.3, 11.5, 'wood', P['wood'], mode='flat')
    for k in range(5):
        for side in (-1.5, 1.5):
            cyl(side, -1.6, -31 - k * 2.6, 0.16, 2.0, 'wood', P['woodDark'], segs=6)
    cyl(0, -1.7, -46, 6.0, 2.2, 'stone', P['stoneDark'], segs=14)
    for i in range(8):
        a = i / 8 * math.tau
        rock(math.cos(a) * 6.2, -0.6, -46 + math.sin(a) * 6.2, 1.6, seed=300 + i)
    for k in range(6):
        cyl(0, 0.5 + k * 2.3, -46, 2.3 - k * 0.12, 2.3, 'plaster', P['white'] if k % 2 == 0 else P['fabricRed'], segs=12, r2=2.3 - (k + 1) * 0.12)
    cyl(0, 14.3, -46, 3.0, 0.3, 'stone', P['stone'], segs=12)
    cyl(0, 14.6, -46, 1.4, 2.0, 'glow', P['glow'], segs=12)
    cyl(0, 16.6, -46, 1.7, 1.4, 'metal', P['metalTeal'], segs=12, r2=0.2)
    door(0, -43.75, 0, 1, P['teal'])

def backdrop():
    """Hills and far rooftops beyond the boundary (visual only)."""
    rnd = random.Random(5)
    for i in range(14):
        x = -100 + i * 15 + rnd.uniform(-4, 4)
        blob(x, -4, 92 + rnd.uniform(-8, 8), 22, 16 + rnd.uniform(0, 10), 14, 'nc_backdrop', hexc('#93a98a'), subdiv=2, seed=500 + i)
    for i in range(26):
        x = -88 + i * 7 + rnd.uniform(-1.5, 1.5)
        h = rnd.uniform(6, 13)
        z = 62 + rnd.uniform(0, 8)
        box(x, 0, z, rnd.uniform(4, 7), h, rnd.uniform(5, 8), 'nc_backdrop', P[rnd.choice(BUILD_TINTS)], mode='world')
        box(x, h, z, 5.5, 0.6, 6.5, 'nc_backdrop', P['roof'], mode='flat')
    for sx in (-1, 1):
        for i in range(6):
            blob(sx * (96 + i * 3), -2, -10 + i * 14, 10, 8 + i, 12, 'nc_backdrop', hexc('#8fa58a'), subdiv=2, seed=600 + i + (9 if sx > 0 else 0))

ground()
half()
centre()
backdrop()

# ----------------------------------------------------------------- build objects, materials
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)

MATS = {
    # name: (base colour multiplier, roughness, metallic, emission, alpha)
    'plaster': (1, 0.85, 0, 0, 1), 'stone': (1, 0.8, 0, 0, 1), 'cobble': (1, 0.9, 0, 0, 1), 'roof': (1, 0.75, 0, 0, 1),
    'wood': (1, 0.7, 0, 0, 1), 'metal': (1, 0.45, 0.6, 0, 1), 'concrete': (1, 0.9, 0, 0, 1), 'sand': (1, 0.95, 0, 0, 1),
    'tiles': (1, 0.4, 0, 0, 1), 'glass': (1, 0.15, 0.3, 0, 1), 'fabric': (1, 0.9, 0, 0, 1), 'crystal': (1, 0.2, 0, 0.35, 1),
    'glow': (1, 0.3, 0, 2.5, 1), 'nc_leaves': (1, 0.8, 0, 0, 1), 'nc_water': (1, 0.08, 0, 0, 0.72), 'nc_backdrop': (1, 0.95, 0, 0, 1),
}

def make_material(name):
    base, rough, metal, emit, alpha = MATS[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes.get('Principled BSDF')
    attr = nt.nodes.new('ShaderNodeVertexColor')
    attr.layer_name = 'Col'
    nt.links.new(attr.outputs['Color'], bsdf.inputs['Base Color'])
    bsdf.inputs['Roughness'].default_value = rough
    bsdf.inputs['Metallic'].default_value = metal
    if emit > 0:
        # Fixed teal emission (exporters can't carry a vertex-colour-driven emission).
        lin = lambda c: (c / 12.92) if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
        h = PAL['glow'] if name == 'glow' else PAL['crystal']
        rgb = [lin(v) for v in hexc(h)[:3]]
        bsdf.inputs['Emission Color'].default_value = (*rgb, 1.0)
        bsdf.inputs['Emission Strength'].default_value = emit
    if alpha < 1:
        bsdf.inputs['Alpha'].default_value = alpha
        try:
            m.surface_render_method = 'BLENDED'
        except Exception:
            m.blend_method = 'BLEND'
    return m

stats = {}
rot = Matrix.Rotation(math.radians(90), 4, 'X')  # game (x, y-up, z) → Blender (x, -z, y)
for name, bm in MBX.bms.items():
    # Every shell is closed: make all normals point outward (fixes axis-swapped / mirrored parts).
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.transform(rot)
    # Soft bevels, crisp silhouettes: smooth shading split at 35°.
    try:
        me.shade_smooth()
        me.set_sharp_from_angle(angle=math.radians(35))
    except Exception as e:
        print('smooth-by-angle unavailable:', e)
    me.update()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    me.materials.append(make_material(name))
    try:
        me.color_attributes.active_color = me.color_attributes['Col']
        me.color_attributes.render_color_index = me.color_attributes.find('Col')
    except Exception:
        pass
    stats[name] = len(me.polygons)

os.makedirs(OUT, exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, 'shardfall.blend'))

# ----------------------------------------------------------------- export glTF
props = bpy.ops.export_scene.gltf.get_rna_type().properties.keys()
kw = dict(filepath=os.path.join(OUT, 'scene.gltf'), export_format='GLTF_SEPARATE', export_yup=True, export_apply=True)
for k, v in [('export_texcoords', False), ('export_normals', True), ('export_materials', 'EXPORT'), ('export_vertex_color', 'ACTIVE'),
             ('export_all_vertex_colors', False), ('export_cameras', False), ('export_lights', False), ('export_extras', False)]:
    if k in props:
        kw[k] = v
bpy.ops.export_scene.gltf(**kw)

tris = 0
for ob in bpy.data.objects:
    if ob.type == 'MESH':
        ob.data.calc_loop_triangles()
        tris += len(ob.data.loop_triangles)
print('SHARDFALL_STATS', stats, 'tris', tris)
