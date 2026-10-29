import numpy as np
import pandas as pd
from sklearn.metrics import mean_poisson_deviance
KEYS=['station_id','time']

def metrics(g):
    e=g.prediction-g.actual
    peak=(g.actual>=g.peak_threshold)&(g.actual>0)
    out={'n':len(g),'mae':float(e.abs().mean()),'rmse':float(np.sqrt((e**2).mean())),
         'bias':float(e.mean()),'macro_station_mae':float(g.assign(ae=e.abs()).groupby('station_id').ae.mean().mean()),
         'poisson_deviance_eps_1e_minus9':float(mean_poisson_deviance(g.actual,np.maximum(g.prediction,1e-9))),
         'peak_n':int(peak.sum()),'peak_mae':float(e[peak].abs().mean()),
         'peak_underprediction_rate':float((e[peak]<0).mean()) if peak.any() else np.nan}
    for label,mask in [('zero',g.actual==0),('one_two',g.actual.between(1,2)),
                       ('three_five',g.actual.between(3,5)),('six_plus',g.actual>=6)]:
        out[label+'_n']=int(mask.sum());out[label+'_mae']=float(e[mask].abs().mean())
    if {'lower','upper'}.issubset(g) and g.lower.notna().all():
        out['interval_coverage']=float(g.actual.between(g.lower,g.upper).mean())
        out['interval_width']=float((g.upper-g.lower).mean())
        for col,q in [('lower',.05),('upper',.95)]:
            err=g.actual-g[col];out[col+'_pinball']=float(np.maximum(q*err,(q-1)*err).mean())
    return out


def assert_same_samples(pred):
    for (split,target),g in pred.groupby(['split','target']):
        reference=None
        for name,sub in g.groupby('model'):
            if sub.duplicated(KEYS).any():raise AssertionError(f'Duplicate samples {split}/{target}/{name}')
            a=sub.sort_values(KEYS)[KEYS+['actual']].reset_index(drop=True)
            if reference is None:reference=a
            else:pd.testing.assert_frame_equal(reference,a,check_dtype=False,check_exact=True)


def paired_bootstrap(candidate,baseline,reps=2000,seed=42):
    a=candidate.sort_values(KEYS).reset_index(drop=True)
    b=baseline.sort_values(KEYS).reset_index(drop=True)
    pd.testing.assert_frame_equal(a[KEYS+['actual']],b[KEYS+['actual']],check_dtype=False,check_exact=True)
    if a.duplicated(KEYS).any():raise AssertionError('Duplicate bootstrap keys')
    d=pd.DataFrame({'date':a.time.dt.floor('D'),'difference':(a.prediction-a.actual).abs()-(b.prediction-b.actual).abs()})
    daily=d.groupby('date').difference.agg(['sum','size'])
    rng=np.random.default_rng(seed)
    ix=rng.integers(0,len(daily),size=(reps,len(daily)))
    samples=daily['sum'].to_numpy()[ix].sum(axis=1)/daily['size'].to_numpy()[ix].sum(axis=1)
    lo,hi=np.quantile(samples,[.025,.975])
    return {'mae_difference':float(d.difference.mean()),'ci_low':float(lo),'ci_high':float(hi),
            'day_blocks':len(daily),'bootstrap_repetitions':reps,
            'inference_scope':'paired_daily_blocks_descriptive_not_selection_adjusted'}


def summarize(pred):
    assert_same_samples(pred)
    rows=[]
    for key,g in pred.groupby(['split','target','model']):
        rows.append({**dict(zip(['split','target','model'],key)),**metrics(g)})
    return pd.DataFrame(rows)


def choose(pred,summary,cfg):
    chosen={};comparisons=[];decisions=[]
    for target in sorted(pred.target.unique()):
        val=pred[(pred.split=='validation')&(pred.target==target)]
        base=val[val.model=='hgb_full']
        bm=metrics(base);eligible=[]
        for name,g in val.groupby('model'):
            pair=paired_bootstrap(g,base,cfg.get('bootstrap_repetitions',2000),cfg.get('seed',42))
            comparisons.append({'target':target,'model':name,**pair})
            m=metrics(g)
            gain=1-m['mae']/bm['mae'] if bm['mae']>0 else 0
            cv=summary[(summary.target==target)&summary.split.str.startswith('cv_')]
            cm=cv[cv.model==name];cb=cv[cv.model=='hgb_full']
            cvmean=np.average(cm.mae,weights=cm.n) if len(cm) else np.nan
            cvbase=np.average(cb.mae,weights=cb.n) if len(cb) else np.nan
            cv_ok=not len(cv) or cvmean<=cvbase*(1+cfg.get('cv_relative_tolerance',.02))
            peak_ok=(not cfg.get('require_peak_not_worse',True) or
                     (m['peak_mae']<=bm['peak_mae'] and m['peak_underprediction_rate']<=bm['peak_underprediction_rate']))
            ci_ok=not cfg.get('require_negative_ci',True) or pair['ci_high']<0
            ok=name!='hgb_full' and gain>cfg.get('minimum_relative_gain',0) and cv_ok and peak_ok and ci_ok
            decisions.append({'target':target,'model':name,'relative_validation_gain':gain,'cv_ok':bool(cv_ok),
                              'peak_ok':bool(peak_ok),'ci_ok':bool(ci_ok),'eligible':bool(ok)})
            if ok:eligible.append((m['mae'],name))
        chosen[target]=min(eligible)[1] if eligible else 'hgb_full'
    return chosen,pd.DataFrame(comparisons),pd.DataFrame(decisions)
