import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def make_plots(eda,pred,metrics,simulation,out,cfg):
    prefix='SYNTHETIC DEMO | ' if cfg.get('synthetic_demo') else ''
    plt.rcParams.update({'figure.dpi':120,'savefig.dpi':180,'axes.grid':True,'grid.alpha':.2})
    def save(fig,name,title):
        fig.suptitle(prefix+title,fontsize=12)
        fig.tight_layout(rect=[0,0,1,.94]);fig.savefig(out/name);plt.close(fig)
    fig,ax=plt.subplots(figsize=(9,3.5));d=eda['daily']
    ax.plot(d.date,d.rides);ax.set_ylabel('Observed trips');fig.autofmt_xdate()
    save(fig,'01_daily.png','Observed daily trips (zero / missing coverage must be audited)')
    fig,ax=plt.subplots(figsize=(8,4))
    for weekend,g in eda['hourly'].groupby('weekend'):
        ax.plot(g.hour,g.observed_rides_per_calendar_slot,label='Weekend' if weekend else 'Weekday')
    ax.set_xlabel('Local hour');ax.set_ylabel('Observed trips per calendar slot');ax.legend()
    save(fig,'02_hourly.png','Hourly profile; denominator includes configured calendar hours')
    fig,axes=plt.subplots(1,2,figsize=(10,4))
    for ax,col in zip(axes,['member_type','bike_type']):
        g=eda['rides'].groupby(col).size()
        ax.bar(g.index.astype(str),g.values);ax.tick_params(axis='x',rotation=20);ax.set_title(col)
    save(fig,'03_groups.png','Observed trip composition')
    p=eda['pattern'].pivot(index='station_id',columns='hour',values='net_outflow')
    fig,ax=plt.subplots(figsize=(10,max(3,len(p)*.22)))
    vmax=max(1,float(np.nanmax(np.abs(p.to_numpy()))))
    im=ax.imshow(p,aspect='auto',cmap='RdBu_r',vmin=-vmax,vmax=vmax)
    ax.set_yticks(range(len(p)),p.index.astype(str));ax.set_xticks(range(len(p.columns)),p.columns)
    ax.set_xlabel('Local hour');fig.colorbar(im,ax=ax,label='Mean departures minus arrivals')
    save(fig,'04_net_flow_heatmap.png','Station hourly flow (not a shortage estimate)')
    s=eda['station'].dropna(subset=['lat','lng'])
    if not s.empty:
        fig,ax=plt.subplots(figsize=(7,5))
        v=max(1,float(s.net_outflow.abs().max()))
        im=ax.scatter(s.lng,s.lat,s=30+150*(s.departures+s.arrivals)/(s.departures+s.arrivals).max(),
                      c=s.net_outflow,cmap='RdBu_r',vmin=-v,vmax=v,edgecolors='black')
        for r in s.itertuples(): ax.annotate(str(r.station_id),(r.lng,r.lat),fontsize=8)
        ax.set_xlabel('Longitude');ax.set_ylabel('Latitude');fig.colorbar(im,ax=ax,label='Net outflow')
        save(fig,'05_station_spatial.png','Station locations (coordinate scatter, not road distances)')
    fig,axes=plt.subplots(1,2,figsize=(12,4))
    for ax,target in zip(axes,['departures','arrivals']):
        g=metrics[(metrics.split=='test')&(metrics.target==target)]
        ax.barh(g.model,g.mae);ax.set_title(target);ax.set_xlabel('Test MAE')
    save(fig,'06_model_comparison.png','Holdout comparison: all fixed candidate models')
    test=pred[(pred.split=='test')&(pred.target=='departures')&(pred.model=='hgb_full')]
    sid=str(test.station_id.iloc[0]);g=test[test.station_id==sid].sort_values('time').head(72)
    fig,ax=plt.subplots(figsize=(11,4));ax.plot(g.time,g.actual,label='Actual');ax.plot(g.time,g.prediction,label='Prediction')
    if 'lower' in g and g.lower.notna().any():
        ax.fill_between(g.time.to_numpy(),g.lower.to_numpy(float),g.upper.to_numpy(float),alpha=.2,label='Nominal 90% interval')
    ax.legend();fig.autofmt_xdate();ax.set_ylabel('Departures')
    save(fig,'07_prediction_example.png',f'First selected station {sid}, first 72 test hours (fixed selection rule)')
    if not simulation.empty:
        pivot=simulation.pivot(index='scenario',columns='strategy',values='service_rate')
        ax=pivot.plot.bar(figsize=(11,4));ax.set_ylim(0,1);ax.set_ylabel('Served / observed requests');ax.tick_params(axis='x',rotation=0)
        save(ax.figure,'08_scenario_simulation.png','ASSUMPTION-BASED REPLAY, not measured operational improvement')
