"""Generic end-camera table finder + calibration (no fixed scan windows).

find_quad(img)        -> rough bed quad (TL,TR,BL,BR) from the largest grey-cloth blob, or None
calibrate_frame(img)  -> (camera params, rms, lines, quad) using 5 lines derived from the quad:
    L,R : side cushion noses (z=-1.43)   T : far cushion base (z=0)
    FS  : foot string chalk line (x=75, z=0)   N : near cushion nose silhouette (x=0, z=-1.43)
Works on any 1920x1080 frame from an "end" overhead camera (looking along the table from behind
one short rail). `img` is a ppm.Img."""
import math
from fitlines import robust
from linefit import fit_lines

S = 4  # sub-sampling step for the coarse pass

CLOTH = None   # None: nỉ xám (WNT 2023); [r,g,b]: nỉ có màu (vd xanh dương WPA 2025), đặt bằng set_cloth()

def set_cloth(rgb):
    global CLOTH
    CLOTH = list(rgb) if rgb else None

def is_cloth(c):
    if CLOTH:
        return abs(c[0]-CLOTH[0])+abs(c[1]-CLOTH[1])+abs(c[2]-CLOTH[2]) < 90
    mx, mn = max(c), min(c); m = (c[0]+c[1]+c[2])/3
    return mx-mn < 32 and 105 < m < 225

def find_quad(im, step=S):
    W, H = im.w//step, im.h//step
    grid = bytearray(W*H)
    for gy in range(H):
        y = gy*step
        for gx in range(W):
            if is_cloth(im.get(gx*step, y)): grid[gy*W+gx] = 1
    seen = bytearray(W*H); best = None
    for i in range(W*H):
        if not grid[i] or seen[i]: continue
        st = [i]; seen[i] = 1; comp = []
        while st:
            j = st.pop(); comp.append(j); x, y = j % W, j//W
            for nb in ((j-1) if x > 0 else -1, (j+1) if x < W-1 else -1, j-W, j+W):
                if 0 <= nb < W*H and grid[nb] and not seen[nb]: seen[nb] = 1; st.append(nb)
        if best is None or len(comp) > len(best): best = comp
    if not best or len(best) < W*H*0.05: return None
    pts = [(j % W, j//W) for j in best]
    TL = min(pts, key=lambda p: p[0]+p[1]); BR = max(pts, key=lambda p: p[0]+p[1])
    TR = max(pts, key=lambda p: p[0]-p[1]); BL = min(pts, key=lambda p: p[0]-p[1])
    q = {k: (v[0]*step, v[1]*step) for k, v in (('TL', TL), ('TR', TR), ('BL', BL), ('BR', BR))}
    q['fill'] = len(best)/max(1, quad_area(q)/(step*step))
    return q

def quad_area(q):
    P = [q['TL'], q['TR'], q['BR'], q['BL']]
    return abs(sum(P[i][0]*P[(i+1) % 4][1]-P[(i+1) % 4][0]*P[i][1] for i in range(4)))/2

def plausible_end_view(q):
    """End camera: narrow far rail at top, horizontal top/bottom edges."""
    if not q: return False
    wt = q['TR'][0]-q['TL'][0]; wb = q['BR'][0]-q['BL'][0]; h = (q['BL'][1]+q['BR'][1]-q['TL'][1]-q['TR'][1])/2
    if wb < 500 or h < 200: return False
    r1, r2 = wt/wb, h/wb
    flat = abs(q['TL'][1]-q['TR'][1]) < 0.05*wb and abs(q['BL'][1]-q['BR'][1]) < 0.05*wb
    return 0.55 < r1 < 0.95 and 0.35 < r2 < 0.75 and flat and q['fill'] > 0.75

def _scan(im, x, y, dx, dy, TH=20, n=3, maxlen=400):
    hist = []; miss = 0; last = None; k = 0
    while 2 < x < im.w-2 and 2 < y < im.h-2 and k < maxlen:
        c = im.get(x, y)
        dif = sum(abs(c[i]-sum(h[i] for h in hist)/len(hist)) for i in range(3)) if len(hist) >= 8 else 0
        if dif < TH: miss = 0; last = (x, y); hist.append(c); hist = hist[-15:]
        else:
            miss += 1
            if miss >= n: return last
        x += dx; y += dy; k += 1
    return None

def _lerp(a, b, t): return (a[0]+(b[0]-a[0])*t, a[1]+(b[1]-a[1])*t)

def detect_lines(im, q):
    TL, TR, BL, BR = q['TL'], q['TR'], q['BL'], q['BR']
    out = {'L': [], 'R': [], 'T': [], 'FS': [], 'N': []}
    for i in range(4, 97, 2):
        t = i/100
        l = _lerp(TL, BL, t); r = _lerp(TR, BR, t); w = r[0]-l[0]
        y = int(round(l[1]+(r[1]-l[1])*0.0))
        if 0.44 < t < 0.56: continue                       # side pockets
        out['L'].append(_scan(im, int(l[0]+0.12*w), int(l[1]), -1, 0))
        out['R'].append(_scan(im, int(r[0]-0.12*w), int(r[1]), 1, 0))
    H = (BL[1]+BR[1]-TL[1]-TR[1])/2
    for i in range(6, 95, 2):
        t = i/100; a = _lerp(TL, TR, t)
        out['T'].append(_scan(im, int(a[0]), int(a[1]+0.18*H), 0, -1, maxlen=int(0.3*H)))
    # foot string: thin bright horizontal line ~ 21% of the way from far to near rail
    for i in range(8, 93, 1):
        t = i/100; a = _lerp(TL, TR, t); b = _lerp(BL, BR, t); x = int(a[0]+(b[0]-a[0])*0.2)
        yc = int(a[1]+0.21*H); lo, hi = yc-int(0.07*H), yc+int(0.07*H)
        f = lambda yy: sum(im.get(x, yy))-(sum(im.get(x, yy-3))+sum(im.get(x, yy+3)))/2
        d0, y = max((f(yy), yy) for yy in range(lo, hi))
        if d0 > 5:
            a1, b1, c1 = f(y-1), f(y), f(y+1); den = a1-2*b1+c1
            out['FS'].append([x, y+(0.5*(a1-c1)/den if den else 0)])
    # near nose silhouette: first small brightness step going down near the bottom edge
    for i in range(8, 93, 1):
        t = i/100; b = _lerp(BL, BR, t); x = int(b[0]); y0 = int(b[1]-0.03*H)
        base = sum(im.get(x, y0))
        for y in range(y0+1, int(b[1]+0.03*H)):
            if sum(im.get(x, y))-base >= 7: out['N'].append([x, y-0.5]); break
    lines = {}
    for k, vert in (('L', 1), ('R', 1), ('T', 0), ('FS', 0), ('N', 0)):
        pts = [p for p in out[k] if p]
        if k == 'FS' and CLOTH and (len(pts) < 8 or robust(pts, vert)[2] < 0.5*len(pts)): continue   # bàn nỉ màu không có vạch phấn
        if len(pts) < 8: return None
        try: a, b, n = robust(pts, vert)
        except ZeroDivisionError: return None
        if n < {'N': 0.4, 'FS': 0.5}.get(k, 0.6)*len(pts): return None   # occluded (player over the rail etc.)
        lines[k] = {'form': 'x=a*y+b' if vert else 'y=a*x+b', 'a': a, 'b': b, 'n': n}
    return lines

def fit_camera(lines, p0=None, hs=1.43, hf=0.0, hn=1.43):
    ln = lambda k: ('v' if lines[k]['form'].startswith('x') else 'h', lines[k]['a'], lines[k]['b'])
    cons = [(ln('L'), [(x, 0, -hs) for x in range(8, 96, 8) if not 44 < x < 56]),
            (ln('R'), [(x, 50, -hs) for x in range(8, 96, 8) if not 44 < x < 56]),
            (ln('T'), [(100, y, -hf) for y in range(4, 48, 4)]),
            (ln('N'), [(0, y, -hn) for y in range(4, 48, 4)])]
    if 'FS' in lines: cons.append((ln('FS'), [(75, y, 0) for y in range(4, 48, 4)]))
    best = None
    for p in ([p0] if p0 else []) + [[-309, 25.7, -115, 0, 0.3, 0, 6128], [-250, 25, -100, 0, 0.35, 0, 5000], [-400, 25, -140, 0, 0.3, 0, 8000]]:
        try: q, cost, r = fit_lines(cons, p)
        except ZeroDivisionError: continue
        if q[2] < 0 and (best is None or cost < best[1]): best = (q, cost, r)
    if not best: return None
    q, cost, r = best
    return q, math.sqrt(cost/len(r))

def calibrate_frame(im, p0=None):
    q = find_quad(im)
    if not plausible_end_view(q): return None
    lines = detect_lines(im, q)
    if not lines: return None
    res = fit_camera(lines, p0)
    if not res: return None
    return res[0], res[1], lines, q
