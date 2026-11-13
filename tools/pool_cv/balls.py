"""Detect balls on the bed in an overhead broadcast frame.
usage: python balls.py frame.ppm calib.json  -> JSON lines, one per ball, sorted by table x
Table frame (inches, 9ft = 100x50): x=0 at the rail nearest the camera -> 100 far rail,
y=0 left rail -> 50 right rail (as seen in the image)."""
import sys, os, json, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ppm import Img
from camera import ray_plane, project
CAM=None

R = 1.125

class Calib:
    """Image <-> table (bed plane z=0) mapping from the fitted pinhole camera."""
    def __init__(s, cal):
        s.cam = cal['camera']
    def to_table(s, p): return ray_plane(s.cam, p, 0.0)
    def to_px(s, t): return project(s.cam, (t[0], t[1], 0.0))[0]

def kasa(pts):
    n = len(pts); sx = sum(p[0] for p in pts)/n; sy = sum(p[1] for p in pts)/n
    U = [p[0]-sx for p in pts]; V = [p[1]-sy for p in pts]
    Suu = sum(u*u for u in U); Svv = sum(v*v for v in V); Suv = sum(u*v for u, v in zip(U, V))
    Suuu = sum(u**3 for u in U); Svvv = sum(v**3 for v in V)
    Suvv = sum(u*v*v for u, v in zip(U, V)); Svuu = sum(v*u*u for u, v in zip(U, V))
    c1 = (Suuu+Suvv)/2; c2 = (Svvv+Svuu)/2; det = Suu*Svv-Suv*Suv
    uc = (c1*Svv-c2*Suv)/det; vc = (Suu*c2-Suv*c1)/det
    return uc+sx, vc+sy, math.sqrt(uc*uc+vc*vc+(Suu+Svv)/n)

def refine(im, cx, cy, r, bed, inb):
    """Radial edge search on the upper ~200 deg of the ball outline, then fixed-radius circle fit."""
    edge = []
    for k in range(-10, 191, 6):            # angle in degrees: 0 = right, 90 = up
        a = math.radians(k); ux, uy = math.cos(a), -math.sin(a)
        def diff(t):
            x, y = cx+ux*t, cy+uy*t
            if not (0 <= x < im.w-1 and 0 <= y < im.h-1): return 0
            c = im.get(int(round(x)), int(round(y)))
            return abs(c[0]-bed[0])+abs(c[1]-bed[1])+abs(c[2]-bed[2])
        inner = sorted(diff(r*f) for f in (0.55, 0.65, 0.75))[1]
        if inner < 40: continue
        th = inner*0.5; t = r*1.45; hit = None
        while t > r*0.6:
            if diff(t) > th: hit = t; break
            t -= 0.25
        if hit is None: continue
        ex, ey = cx+ux*(hit+0.125), cy+uy*(hit+0.125)
        if inb(ex, ey, -0.2): edge.append((ex, ey))
    if len(edge) < 8: return cx, cy
    for _ in range(20):
        a11=a12=a22=b1=b2=0
        for ex, ey in edge:
            dx, dy = ex-cx, ey-cy; d = math.hypot(dx, dy) or 1e-6
            rd = d-r; jx, jy = -dx/d, -dy/d
            if abs(rd) > 3: continue
            a11+=jx*jx; a12+=jx*jy; a22+=jy*jy; b1+=jx*rd; b2+=jy*rd
        det = a11*a22-a12*a12
        if abs(det) < 1e-9: break
        sx = -(a22*b1-a12*b2)/det; sy = -(a11*b2-a12*b1)/det; cx += sx; cy += sy
        if abs(sx)+abs(sy) < 1e-3: break
    return cx, cy

def detect(path, cal):
    global CAM
    im = Img(path); K = Calib(cal); CAM = cal.get('camera')
    def inb(x, y, m): u, v = K.to_table((x, y)); return -m <= u <= 100+m and -m <= v <= 50+m
    cs = [K.to_px(t) for t in ((0, 0), (100, 0), (0, 50), (100, 50))]
    x0 = int(min(c[0] for c in cs))-3; x1 = int(max(c[0] for c in cs))+3
    y0 = int(min(c[1] for c in cs))-3; y1 = int(max(c[1] for c in cs))+3
    ref = {}
    for y in range(y0, y1):
        c = [im.get(x, y) for x in range(x0, x1, 7) if inb(x, y, -1.5)]
        if c: ref[y] = tuple(sorted(q[i] for q in c)[len(c)//2] for i in range(3))
    TH = cal.get('ball_diff', 55); M = cal.get('bed_margin_in', 0.25)
    mask = set(); bedok = {}
    for y in range(y0, y1):
        r = ref.get(y)
        if not r: continue
        for x in range(x0, x1):
            if not inb(x, y, M): continue
            c = im.get(x, y)
            if abs(c[0]-r[0])+abs(c[1]-r[1])+abs(c[2]-r[2]) > TH: mask.add((x, y))
    GAP = [(a, b) for a in range(-3, 4) for b in range(-3, 4) if a or b]
    seen = set(); out = []
    for p in mask:
        if p in seen: continue
        st = [p]; seen.add(p); comp = []
        while st:
            q = st.pop(); comp.append(q)
            for d in GAP:
                nb = (q[0]+d[0], q[1]+d[1])
                if nb in mask and nb not in seen: seen.add(nb); st.append(nb)
        if len(comp) < 150: continue
        rows = {}
        for x, y in comp: rows.setdefault(y, []).append(x)
        ymin = min(rows)
        r_est = max(max(v)-min(v)+1 for y, v in rows.items() if y < ymin+40)/2
        pts = []
        for y, v in rows.items():
            if y <= ymin+1.1*r_est:
                for xe in (min(v)-0.5, max(v)+0.5):
                    if inb(xe, y, -0.2): pts.append((xe, y))
        pts += [(x, ymin-0.5) for x in rows[ymin] if inb(x, ymin, -0.2)]
        if len(pts) < 12: continue
        cx, cy, r = kasa(pts)
        if CAM:
            for _ in range(3):
                tx, ty = ray_plane(CAM, (cx, cy), -R); _, zc = project(CAM, (tx, ty, -R)); rp = CAM[6]*R/zc
                ref_c = ref.get(int(cy)) or ref[min(ref, key=lambda k: abs(k-cy))]
                cx, cy = refine(im, cx, cy, rp, ref_c, inb)
        if CAM:
            tx, ty = ray_plane(CAM, (cx, cy), -R); _, zc = project(CAM, (tx, ty, -R)); rp = CAM[6]*R/zc
        else:
            tx, ty = K.to_table((cx, cy+r)); tx += cal.get('bottom_point_dx_in', 0.18); rp = None
        a = K.to_px((tx, ty-1)); b = K.to_px((tx, ty+1)); pxy = math.dist(a, b)/2
        a = K.to_px((tx-1, ty)); b = K.to_px((tx+1, ty)); pxx = math.dist(a, b)/2
        if not (30 < cx < im.w-30 and 30 < cy < im.h-30) or not (0.6*rp < r < 1.6*rp if rp else True): continue
        rr = int(r*.55)
        cols = [im.get(int(cx+dx), int(cy+dy)) for dx in range(-rr, rr+1, 2) for dy in range(-rr, rr+1, 2) if dx*dx+dy*dy < rr*rr]
        mc = [round(sum(c[i] for c in cols)/len(cols)) for i in range(3)]
        bright = sum(1 for c in cols if min(c) > 200)/len(cols)
        out.append({'px': [round(cx, 1), round(cy, 1)], 'r_px': round(r, 1), 'r_exp': round(rp if rp else R*pxy, 1),
                    'elev': round(math.degrees(math.asin(min(1, pxx/pxy))), 1), 'n': len(comp),
                    'rgb': mc, 'white_frac': round(bright, 2), 'table': [round(tx, 2), round(ty, 2)]})
    out.sort(key=lambda b: b['table'][0])
    return out

if __name__ == '__main__':
    for b in detect(sys.argv[1], json.load(open(sys.argv[2]))): print(json.dumps(b))
