import math
from camera import project, solve
# image line forms: ('v',a,b): x=a*y+b ; ('h',a,b): y=a*x+b
def dist(line,u,v):
    k,a,b=line
    if k=='v': return (u-(a*v+b))/math.sqrt(1+a*a)
    return (v-(a*u+b))/math.sqrt(1+a*a)
def fit_lines(cons, p0, iters=300, extra=()):
    """cons: list of (image_line, [world points]); extra: list of (world_pt, px, weight)"""
    p=list(p0); lam=1e-3
    def resid(p):
        r=[]
        for line,W in cons:
            for P in W:
                (u,v),_=project(p,P); r.append(dist(line,u,v))
        for P,px,w in extra:
            (u,v),_=project(p,P); r+= [w*(u-px[0]), w*(v-px[1])]
        return r
    r=resid(p); cost=sum(x*x for x in r); steps=[1,1,1,1e-4,1e-4,1e-4,1]
    for _ in range(iters):
        J=[]
        for k in range(7):
            q=p[:];q[k]+=steps[k];rq=resid(q);J.append([(a-b)/steps[k] for a,b in zip(rq,r)])
        JtJ=[[sum(J[i][m]*J[j][m] for m in range(len(r))) for j in range(7)] for i in range(7)]
        Jtr=[sum(J[i][m]*r[m] for m in range(len(r))) for i in range(7)]
        while True:
            A=[[JtJ[i][j]*(1+lam if i==j else 1) for j in range(7)] for i in range(7)]
            dp=solve(A,[-x for x in Jtr]);q=[a+b for a,b in zip(p,dp)];rq=resid(q);cq=sum(x*x for x in rq)
            if cq<cost: p,r,cost,lam=q,rq,cq,lam*0.3;break
            lam*=10
            if lam>1e12: return p,cost,r
        if max(abs(x) for x in dp)<1e-9: break
    return p,cost,r
