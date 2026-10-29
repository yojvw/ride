from dataclasses import dataclass
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.dummy import DummyRegressor
from threadpoolctl import threadpool_limits
from .panel import feature_columns

@dataclass
class FittedCountModel:
    estimator: object
    columns: list
    features: list

    def predict(self,frame):
        x=design(frame,self.features).reindex(columns=self.columns,fill_value=0)
        with threadpool_limits(limits=1):
            return np.maximum(0,self.estimator.predict(x))


def design(frame,cols):
    x=frame[cols].copy()
    d=pd.get_dummies(frame.station_id.astype(str),prefix='station',dtype=float)
    return pd.concat([x,d],axis=1)


def fit_model(frame,target,stage,cfg,quantile=None):
    cols=feature_columns(target,stage)
    x=design(frame,cols)
    y=frame[target].to_numpy()
    if y.sum()==0:
        model=DummyRegressor(strategy='constant',constant=0)
    else:
        kw=dict(max_iter=cfg.get('max_iter',80),max_leaf_nodes=15,min_samples_leaf=15,
                l2_regularization=1.0,early_stopping=False,random_state=cfg.get('seed',42))
        if quantile is None:
            model=HistGradientBoostingRegressor(loss='poisson',**kw)
        else:
            model=HistGradientBoostingRegressor(loss='quantile',quantile=quantile,**kw)
    with threadpool_limits(limits=1):
        model.fit(x,y)
    return FittedCountModel(model,list(x.columns),cols)


def historical_mean(train,test,target):
    means=train.groupby(['station_id','weekday','hour'])[target].mean()
    key=pd.MultiIndex.from_frame(test[['station_id','weekday','hour']])
    pred=means.reindex(key).to_numpy()
    station_mean=train.groupby('station_id')[target].mean()
    fallback=test.station_id.map(station_mean).fillna(train[target].mean()).to_numpy()
    return np.where(np.isnan(pred),fallback,pred)


def predict_split(train,test,target,cfg,split,stages,interval=False):
    cols=feature_columns(target,'full')
    train=train.dropna(subset=[target]+cols)
    test=test.dropna(subset=[target]+cols)
    if len(train)<cfg.get('min_training_rows',100) or len(test)==0:
        raise ValueError(f'Insufficient data for {split}/{target}: train={len(train)}, test={len(test)}')
    preds={'previous_day':test[f'{target}_lag_24'].to_numpy(),
           'historical_mean':historical_mean(train,test,target)}
    for stage in stages:
        preds['hgb_'+stage]=fit_model(train,target,stage,cfg).predict(test)
    pieces=[]
    for name,values in preds.items():
        p=test[['station_id','time',target]].rename(columns={target:'actual'}).copy()
        p['prediction']=values
        p['model']=name
        p['target']=target
        p['split']=split
        threshold=train.groupby('station_id')[target].quantile(.9)
        p['peak_threshold']=p.station_id.map(threshold)
        pieces.append(p)
    result=pd.concat(pieces,ignore_index=True)
    if interval:
        lo=fit_model(train,target,'full',cfg,.05).predict(test)
        hi=fit_model(train,target,'full',cfg,.95).predict(test)
        mask=result.model=='hgb_full'
        result.loc[mask,'lower']=np.minimum(lo,hi)
        result.loc[mask,'upper']=np.maximum(lo,hi)
    return result


def run_forecast(features,cfg):
    t=features.time
    a,b=pd.Timestamp(cfg['train_end']),pd.Timestamp(cfg['validation_end'])
    all_results=[]
    rolling=[]
    nfolds=cfg.get('rolling_folds',2)
    days=cfg.get('rolling_validation_days',2)
    for i in range(nfolds):
        end=a-pd.Timedelta(days=days*(nfolds-1-i))
        begin=end-pd.Timedelta(days=days)
        rolling.append((f'cv_{i+1}',features[t<begin],features[(t>=begin)&(t<end)]))
    for target in ['departures','arrivals']:
        for name,tr,te in rolling:
            all_results.append(predict_split(tr,te,target,cfg,name,['full']))
        all_results.append(predict_split(features[t<a],features[(t>=a)&(t<b)],target,cfg,'validation',
                                         ['calendar','own_history','full']))
        all_results.append(predict_split(features[t<b],features[t>=b],target,cfg,'test',
                                         ['calendar','own_history','full'],cfg.get('prediction_intervals',True)))
    predictions=pd.concat(all_results,ignore_index=True)
    chosen={}
    for target in ['departures','arrivals']:
        g=predictions[(predictions.split=='validation')&(predictions.target==target)].copy()
        g['absolute_error']=(g.actual-g.prediction).abs()
        chosen[target]=str(g.groupby('model').absolute_error.mean().idxmin())
    return predictions,chosen
