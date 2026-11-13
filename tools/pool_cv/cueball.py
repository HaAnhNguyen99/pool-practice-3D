"""Find the cue ball: bright-white cluster + fixed-radius circle fit (radius from camera model).
usage: python cueball.py frame.ppm calib.json"""
import sys, os, json, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ppm import Img
from camera import ray_plane, project
R = 1.125
def find(path, cal, thr=185):
    im = Img(path); cam = cal['camera']
    def tab(px): return ray_plane(cam, px, 0.0)
    pts = set()
    for y in range(360, 900):
        for x in range(440, 1480):
            c = im.get(x, y)
            if min(c) > thr and max(c)-min(c) < 70:
                u, v = tab((x, y))
                if -1 < u < 101 and -1 < v < 51: pts.add((x, y))
    seen = set(); res = []
    for p in pts:
        if p in seen: continue
        st = [p]; seen.add(p); comp = []
        while st:
            q = st.pop(); comp.append(q)
            for d in ((1,0),(-1,0),(0,1),(0,-1),(1,1),(-1,-1),(1,-1),(-1,1)):
                n = (q[0]+d[0], q[1]+d[1])
                if n in pts and n not in seen: seen.add(n); st.append(n)
        if len(comp) < 60: continue
        rows = {}
        for x, y in comp: rows.setdefault(y, []).append(x)
        edge = []
        for y, v in rows.items(): edge += [(min(v)-0.5, y), (max(v)+0.5, y)]
        ymin = min(rows); edge += [(x, ymin-0.5) for x in rows[ymin]]
        cx = sum(e[0] for e in edge)/len(edge); cy = ymin + 19
        for _ in range(30):
            tx, ty = ray_plane(cam, (cx, cy), -R); _, zc = project(cam, (tx, ty, -R)); r = cam[6]*R/zc
            # only use edge points in the upper half of the circle (lower half is shaded, not 'bright')
            E = [e for e in edge if e[1] <= cy + 0.2*r]
            # Gauss-Newton on (cx,cy) with fixed r
            a11=a12=a22=b1=b2=0
            for ex, ey in E:
                dx, dy = ex-cx, ey-cy; d = math.hypot(dx, dy) or 1e-6
                rd = d - r; jx, jy = -dx/d, -dy/d
                a11 += jx*jx; a12 += jx*jy; a22 += jy*jy; b1 += jx*rd; b2 += jy*rd
            det = a11*a22-a12*a12
            if abs(det) < 1e-9: break
            sx = -(a22*b1-a12*b2)/det; sy = -(a11*b2-a12*b1)/det
            cx += sx; cy += sy
            if abs(sx)+abs(sy) < 1e-3: break
        rms = math.sqrt(sum((math.hypot(e[0]-cx, e[1]-cy)-r)**2 for e in E)/len(E))
        tx, ty = ray_plane(cam, (cx, cy), -R)
        res.append({'px': [round(cx, 1), round(cy, 1)], 'r': round(r, 1), 'n': len(comp), 'rms': round(rms, 2), 'table': [round(tx, 2), round(ty, 2)]})
    return res
if __name__ == '__main__':
    for b in find(sys.argv[1], json.load(open(sys.argv[2]))): print(json.dumps(b))
