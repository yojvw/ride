
import pandas as pd, numpy as np, json
pd.set_option('display.width',200)
rides=pd.read_csv("data/clean/rides.csv", dtype={"ride_id":"string","start_station_id":"string","end_station_id":"string"}, parse_dates=["started_at","ended_at"])
start=pd.Timestamp("2024-01-01"); end=pd.Timestamp("2024-02-01")
print("rides", len(rides), rides.started_at.min(), rides.started_at.max())
r=rides[(rides.started_at>=start)&(rides.started_at<end)].copy()
print("in window by started_at", len(r))
# hourly profile
h=r.groupby(r.started_at.dt.hour).size()
print("\nhourly all:\n", h.to_string())
r["weekend"]=r.started_at.dt.dayofweek>=5
print("\nhourly weekday vs weekend (mean per day):")
days_wd=r[r.weekend==False].started_at.dt.normalize().nunique(); days_we=r[r.weekend==True].started_at.dt.normalize().nunique()
print("weekday days",days_wd,"weekend days",days_we)
prof=r.groupby([r.weekend,r.started_at.dt.hour]).size().unstack(fill_value=0)
prof.loc[False]=(prof.loc[False]/days_wd).round(1); prof.loc[True]=(prof.loc[True]/days_we).round(1)
print(prof.to_string())
print("\nweekday counts:", r.started_at.dt.dayofweek.value_counts().sort_index().to_dict())
# member/bike
print("\nmember:", r.member_type.value_counts().to_dict())
print("bike:", r.bike_type.value_counts().to_dict())
print("\nmember x bike:")
print(pd.crosstab(r.member_type, r.bike_type).to_string())
print("\nduration by member (median/mean/p90):")
print(r.groupby("member_type").duration_min.agg(['median','mean',lambda s: s.quantile(.9)]).round(2).to_string())
print("\nduration by bike:")
print(r.groupby("bike_type").duration_min.agg(['median','mean',lambda s: s.quantile(.9)]).round(2).to_string())
print("\nmember share by hour (member count / total):")
sh=r.groupby(r.started_at.dt.hour).member_type.apply(lambda s:(s=="member").mean()).round(3)
print(sh.to_string())
print("\nbike share by hour (electric):")
sh2=r.groupby(r.started_at.dt.hour).bike_type.apply(lambda s:(s=="electric").mean()).round(3)
print(sh2.to_string())
# station totals
dep=r.groupby("start_station_id").size().rename("departures")
arr=r[r.ended_at<end].groupby("end_station_id").size().rename("arrivals")
st=pd.concat([dep,arr],axis=1).fillna(0)
st["events"]=st.departures+st.arrivals
st["net"]=st.departures-st.arrivals
print("\nstations with any endpoint:", len(st))
print("top 10 by events:\n", st.nlargest(10,"events").round(0).to_string())
print("\ntop 10 by net outflow:\n", st.nlargest(10,"net").round(0).to_string())
print("\ntop 10 by net inflow:\n", st.nsmallest(10,"net").round(0).to_string())
print("\nSpearman events vs |net|:", round(st.events.corr(st.net.abs(), method='spearman'),3))
print("Spearman |net| vs volume rank overlap: top20 by events vs top20 by |net| overlap =",
      len(set(st.nlargest(20,'events').index)&set(st.net.abs().nlargest(20).index)))
