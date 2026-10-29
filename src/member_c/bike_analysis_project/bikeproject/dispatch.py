import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp


def distance_km(a,b):
    lat1,lon1=np.radians(a);lat2,lon2=np.radians(b)
    x=np.sin((lat2-lat1)/2)**2+np.cos(lat1)*np.cos(lat2)*np.sin((lon2-lon1)/2)**2
    return float(6371*2*np.arcsin(np.sqrt(np.clip(x,0,1))))


def plan_moves(inventory,capacity,departures,arrivals,coords,budget,method='greedy',buffer=2,distance_weight=.03):
    ids=sorted(inventory)
    target={s:min(capacity[s],max(buffer,int(np.ceil(departures.get(s,0)-arrivals.get(s,0)+buffer)))) for s in ids}
    supply={s:max(0,inventory[s]-target[s]) for s in ids}
    need={s:max(0,target[s]-inventory[s]) for s in ids}
    edges=[(a,b,distance_km(coords[a],coords[b])) for a in ids for b in ids if supply[a]>0 and need[b]>0 and a!=b]
    if not edges or budget<=0:
        return [],{'solver':'none','status':'no_feasible_moves','message':''}
    def greedy():
        ss=supply.copy();nn=need.copy();left=int(budget);moves=[]
        for a,b,d in sorted(edges,key=lambda z:(-need[z[1]],z[2],z[0],z[1])):
            k=min(ss[a],nn[b],left)
            if k:
                moves.append((a,b,int(k),d));ss[a]-=k;nn[b]-=k;left-=k
        return moves
    if method=='greedy':
        return greedy(),{'solver':'greedy','status':'heuristic','message':''}
    if method!='milp': raise ValueError('Unknown dispatch method')
    A=[];ub=[]
    for sid in ids:
        A.append([1 if a==sid else 0 for a,b,d in edges]);ub.append(supply[sid])
        A.append([1 if b==sid else 0 for a,b,d in edges]);ub.append(need[sid])
    A.append([1]*len(edges));ub.append(int(budget))
    cost=np.array([-1+distance_weight*d for a,b,d in edges])
    upper=np.array([min(supply[a],need[b],budget) for a,b,d in edges])
    try:
        result=milp(c=cost,integrality=np.ones(len(edges)),bounds=Bounds(np.zeros(len(edges)),upper),
                    constraints=LinearConstraint(np.array(A,dtype=float),-np.inf,np.array(ub)),
                    options={'time_limit':2.0})
        if result.success and result.x is not None:
            x=np.rint(result.x).astype(int)
            if (np.array(A)@x<=np.array(ub)+1e-6).all() and (x>=0).all():
                return [(a,b,int(k),d) for (a,b,d),k in zip(edges,x) if k],{
                    'solver':'milp','status':'optimal','message':str(result.message)}
        return greedy(),{'solver':'milp','status':'fallback_greedy','message':str(result.message)}
    except (ValueError,RuntimeError) as exc:
        return greedy(),{'solver':'milp','status':'fallback_greedy','message':str(exc)}
