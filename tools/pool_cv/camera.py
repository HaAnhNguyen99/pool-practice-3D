"""Pinhole camera model for an overhead broadcast view of a pool table.
World frame (inches): x along the table (0 = rail nearest camera, 100 = far rail for 9ft),
y across (0 = left rail in image, 50 = right rail), z DOWN (bed z=0, ball centre z=-1.125).
Params p = [X, Y, Z, yaw, pitch, roll, f]; principal point = image centre."""
import math

W, H_IMG = 1920, 1080

def rot(p):
    yaw, pitch, roll = p[3], p[4], p[5]
    # forward/right/down basis before roll
    cp, sp, cy, sy = math.cos(pitch), math.sin(pitch), math.cos(yaw), math.sin(yaw)
    fwd = (cp*cy, cp*sy, sp)
    right = (-sy, cy, 0.0)
    down = (fwd[1]*right[2]-fwd[2]*right[1], fwd[2]*right[0]-fwd[0]*right[2], fwd[0]*right[1]-fwd[1]*right[0])
    # down = fwd x right  (so that right x down = fwd)
    cr, sr = math.cos(roll), math.sin(roll)
    r2 = tuple(cr*a + sr*b for a, b in zip(right, down))
    d2 = tuple(-sr*a + cr*b for a, b in zip(right, down))
    return r2, d2, fwd

def project(p, P):
    r, d, f_ = rot(p)
    v = (P[0]-p[0], P[1]-p[1], P[2]-p[2])
    xc = sum(a*b for a, b in zip(r, v)); yc = sum(a*b for a, b in zip(d, v)); zc = sum(a*b for a, b in zip(f_, v))
    return (p[6]*xc/zc + W/2, p[6]*yc/zc + H_IMG/2), zc

def ray_plane(p, px, z):
    """Intersect the camera ray through pixel px with the plane at height z (z down)."""
    r, d, f_ = rot(p)
    a = (px[0]-W/2)/p[6]; b = (px[1]-H_IMG/2)/p[6]
    dirv = tuple(f_[i] + a*r[i] + b*d[i] for i in range(3))
    t = (z - p[2]) / dirv[2]
    return (p[0]+t*dirv[0], p[1]+t*dirv[1])

def solve(A, b):
    n = len(b); M = [r[:] + [b[i]] for i, r in enumerate(A)]
    for c in range(n):
        piv = max(range(c, n), key=lambda r: abs(M[r][c])); M[c], M[piv] = M[piv], M[c]
        for r in range(n):
            if r != c:
                f = M[r][c]/M[c][c]
                for k in range(c, n+1): M[r][k] -= f*M[c][k]
    return [M[i][n]/M[i][i] for i in range(n)]

def fit(obs, p0, iters=200):
    """obs: list of (world_xyz, pixel_xy[, weight]). Levenberg-Marquardt with numeric Jacobian."""
    p = list(p0); lam = 1e-3
    def resid(p):
        out = []
        for o in obs:
            w = o[2] if len(o) > 2 else 1.0
            (u, v), _ = project(p, o[0]); out += [w*(u-o[1][0]), w*(v-o[1][1])]
        return out
    r = resid(p); cost = sum(x*x for x in r)
    steps = [1.0, 1.0, 1.0, 1e-4, 1e-4, 1e-4, 1.0]
    for _ in range(iters):
        J = []
        for k in range(7):
            q = p[:]; q[k] += steps[k]; rq = resid(q)
            J.append([(a-b)/steps[k] for a, b in zip(rq, r)])
        JtJ = [[sum(J[i][m]*J[j][m] for m in range(len(r))) for j in range(7)] for i in range(7)]
        Jtr = [sum(J[i][m]*r[m] for m in range(len(r))) for i in range(7)]
        while True:
            A = [[JtJ[i][j]*(1+lam if i == j else 1) for j in range(7)] for i in range(7)]
            dp = solve(A, [-x for x in Jtr]); q = [a+b for a, b in zip(p, dp)]
            rq = resid(q); cq = sum(x*x for x in rq)
            if cq < cost: p, r, cost, lam = q, rq, cq, lam*0.3; break
            lam *= 10
            if lam > 1e12: return p, cost
        if max(abs(x) for x in dp) < 1e-9: break
    return p, cost
