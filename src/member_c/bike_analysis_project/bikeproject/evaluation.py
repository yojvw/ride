import numpy as np
import pandas as pd


def score(g):
    e=g.prediction-g.actual
    peak=g.actual>=g.peak_threshold
    positive_peak=peak&(g.actual>0)
    row={'n':len(g),'mae':float(e.abs().mean()),'rmse':float(np.sqrt((e**2).mean())),
         'bias':float(e.mean()),'peak_n':int(positive_peak.sum()),
         'peak_mae':float(e[positive_peak].abs().mean()),
         'peak_underprediction_rate':float((e[positive_peak]<0).mean()) if positive_peak.any() else np.nan}
    if 'lower' in g and g.lower.notna().any():
        m=g.lower.notna()&g.upper.notna()
        row['interval_coverage']=float(((g.loc[m,'actual']>=g.loc[m,'lower'])&(g.loc[m,'actual']<=g.loc[m,'upper'])).mean())
        row['interval_mean_width']=float((g.loc[m,'upper']-g.loc[m,'lower']).mean())
    return row


def tables(pred):
    summary=[]; per_station=[]; per_hour=[]
    for key,g in pred.groupby(['split','target','model']):
        base=dict(zip(['split','target','model'],key))
        row={**base,**score(g)}
        maes=g.assign(abs_error=(g.actual-g.prediction).abs()).groupby('station_id').abs_error.mean()
        row['macro_station_mae']=float(maes.mean())
        summary.append(row)
        for sid,sub in g.groupby('station_id'):
            per_station.append({**base,'station_id':sid,**score(sub)})
        for hour,sub in g.groupby(g.time.dt.hour):
            per_hour.append({**base,'hour':hour,**score(sub)})
    summary=pd.DataFrame(summary)
    base=summary[summary.model=='previous_day'][['split','target','mae']].rename(columns={'mae':'baseline_mae'})
    summary=summary.merge(base,on=['split','target'],validate='many_to_one')
    summary['mae_improvement_vs_previous_day']=np.where(summary.baseline_mae>0,1-summary.mae/summary.baseline_mae,np.nan)
    worst=pred[pred.split=='test'].copy()
    worst['absolute_error']=(worst.actual-worst.prediction).abs()
    return summary,pd.DataFrame(per_station),pd.DataFrame(per_hour),worst.sort_values('absolute_error',ascending=False).head(100)
