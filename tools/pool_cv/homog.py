def solve(A,b):
    n=len(b);M=[r[:]+[b[i]] for i,r in enumerate(A)]
    for c in range(n):
        p=max(range(c,n),key=lambda r:abs(M[r][c]));M[c],M[p]=M[p],M[c]
        for r in range(n):
            if r!=c:
                f=M[r][c]/M[c][c]
                for k in range(c,n+1): M[r][k]-=f*M[c][k]
    return [M[i][n]/M[i][i] for i in range(n)]
def homography(src,dst):
    A=[];b=[]
    for (x,y),(u,v) in zip(src,dst):
        A.append([x,y,1,0,0,0,-u*x,-u*y]);b.append(u)
        A.append([0,0,0,x,y,1,-v*x,-v*y]);b.append(v)
    h=solve(A,b);return [h[0:3],h[3:6],h[6:8]+[1]]
def apply(H,p):
    x,y=p;w=H[2][0]*x+H[2][1]*y+H[2][2]
    return ((H[0][0]*x+H[0][1]*y+H[0][2])/w,(H[1][0]*x+H[1][1]*y+H[1][2])/w)
def inv(H):
    a,b,c=H[0];d,e,f=H[1];g,h,i=H[2]
    A=e*i-f*h;B=-(d*i-f*g);C=d*h-e*g
    det=a*A+b*B+c*C
    return [[A/det,-(b*i-c*h)/det,(b*f-c*e)/det],[B/det,(a*i-c*g)/det,-(a*f-c*d)/det],[C/det,-(a*h-b*g)/det,(a*e-b*d)/det]]
def homography_lsq(src,dst):
    A=[];b=[]
    for (x,y),(u,v) in zip(src,dst):
        A.append([x,y,1,0,0,0,-u*x,-u*y]);b.append(u)
        A.append([0,0,0,x,y,1,-v*x,-v*y]);b.append(v)
    AtA=[[sum(A[k][i]*A[k][j] for k in range(len(A))) for j in range(8)] for i in range(8)]
    Atb=[sum(A[k][i]*b[k] for k in range(len(A))) for i in range(8)]
    h=solve(AtA,Atb);return [h[0:3],h[3:6],h[6:8]+[1]]
