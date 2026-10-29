from dataclasses import dataclass
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.dummy import DummyRegressor
from threadpoolctl import threadpool_limits


def registry(cfg):
    original=int(cfg.get('baseline_max_iter',80))
    return [
      {'name':'hgb_full','features':'base','loss':'poisson','max_iter':original},
      {'name':'adaptive_poisson','features':'adaptive','loss':'poisson','max_iter':original},
      {'name':'adaptive_mae','features':'adaptive','loss':'absolute_error','max_iter':original},
      {'name':'adaptive_recent','features':'adaptive','loss':'poisson','max_iter':original,'half_life_hours':72},
      {'name':'adaptive_longer','features':'adaptive','loss':'poisson','max_iter':int(cfg.get('longer_max_iter',160))},
      {'name':'blend_mean_median','kind':'blend','parts':['adaptive_poisson','adaptive_mae'],'weights':[.5,.5]}
    ]


def design(frame,cols):
    return pd.concat([frame[cols],pd.get_dummies(frame.station_id.astype(str),prefix='station',dtype=float)],axis=1)

@dataclass
class Fitted:
    model:object
    columns:list
    numeric:list
    def predict(self,frame):
        x=design(frame,self.numeric).reindex(columns=self.columns,fill_value=0)
        with threadpool_limits(limits=1):return np.maximum(0,self.model.predict(x))


def fit(frame,target,spec,base_cols,extra,cfg,quantile=None):
    cols=list(base_cols)+(extra if spec.get('features')=='adaptive' else [])
    x=design(frame,cols);y=frame[target].to_numpy(float)
    if y.sum()==0:
        model=DummyRegressor(strategy='constant',constant=0)
    else:
        args=dict(max_iter=spec['max_iter'],max_leaf_nodes=15,min_samples_leaf=15,l2_regularization=1.,
                  early_stopping=False,random_state=cfg.get('seed',42),learning_rate=spec.get('learning_rate',.1))
        model=HistGradientBoostingRegressor(loss='quantile' if quantile else spec['loss'],
                                           **({'quantile':quantile} if quantile else {}),**args)
    weights=None
    if spec.get('half_life_hours'):
        age=(frame.time.max()-frame.time).dt.total_seconds().to_numpy()/3600
        weights=np.exp2(-age/spec['half_life_hours'])
        weights=weights/weights.mean()
    with threadpool_limits(limits=1):model.fit(x,y,sample_weight=weights)
    return Fitted(model,list(x.columns),cols)


def fit_predict_candidates(train,test,target,specs,base_cols,extra,cfg,baseline_fit=None,names=None):
    lookup={s['name']:s for s in specs};cache={}
    def one(name):
        if name in cache:return cache[name]
        s=lookup[name]
        if s.get('kind')=='blend':
            value=sum(w*one(n) for n,w in zip(s['parts'],s['weights']))
        elif name=='hgb_full' and baseline_fit is not None:
            value=baseline_fit(train,target).predict(test)
        else:value=fit(train,target,s,base_cols,extra,cfg).predict(test)
        cache[name]=np.maximum(0,value)
        return cache[name]
    return {n:one(n) for n in (names or list(lookup))}
