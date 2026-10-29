
import pandas as pd, numpy as np
pd.set_option('display.width',220)
rides=pd.read_csv("data/clean/rides.csv", dtype={"start_station_id":"string","end_station_id":"string"}, parse_dates=["started_at","ended_at"])
start=pd.Timestamp("2024-01-01"); end=pd.Timestamp("2024-02-01")
r=rides[(rides.started_at>=start)&(rides.started_at<end)]
dep=r.dropna(subset=["start_station_id"]).assign(h=r.started_at.dt.floor("h"), sid=lambda d:d.start_station_id, kind="dep")
arr=r[(r.ended_at>=start)&(r.ended_at<end)].dropna(subset=["end_station_id"]).assign(h=lambda d:d.ended_at.dt.floor("h"), sid=lambda d:d.end_station_id, kind="arr")
ev=pd.concat([dep[["sid","h","kind"]],arr[["sid","h","kind"]]])
cnt=ev.groupby(["sid","h","kind"]).size().unstack(fill_value=0)
cnt=cnt.reindex(columns=["dep","arr"],fill_value=0)
cnt["net"]=cnt.dep-cnt.arr
cnt["hour"]=cnt.index.get_level_values(1).hour
cnt["date"]=cnt.index.get_level_values(1).normalize()
per=cnt.groupby(["sid","hour"]).net.mean().unstack()   # mean net per station-hour by clock hour
tot=cnt.groupby("sid").agg(dep=("dep","sum"),arr=("arr","sum"))
tot["events"]=tot.dep+tot.arr; tot["net"]=tot.dep-tot.arr
am=per.loc[:,6:9].mean(axis=1); pm=per.loc[:,16:19].mean(axis=1)
tide=pd.DataFrame({"am_net":am,"pm_net":pm}).join(tot)
tide["reversal"]=np.sign(tide.am_net)*np.sign(tide.pm_net)<0
big=tide[tide.events>=200]
print("stations with >=200 events:", len(big))
print("reversal share:", round(big.reversal.mean(),3), int(big.reversal.sum()), "/", len(big))
print("corr(am,pm) all:", round(big.am_net.corr(big.pm_net),3), "spearman:", round(big.am_net.corr(big.pm_net,method='spearman'),3))
print("\nstrongest AM-out / PM-in (commuter source):")
print(big[(big.am_net>0)&(big.pm_net<0)].assign(amp=lambda d:d.am_net-d.pm_net).nlargest(8,"amp")[["am_net","pm_net","events","net"]].round(2).to_string())
print("\nstrongest AM-in / PM-out (commuter sink):")
print(big[(big.am_net<0)&(big.pm_net>0)].assign(amp=lambda d:d.pm_net-d.am_net).nlargest(8,"amp")[["am_net","pm_net","events","net"]].round(2).to_string())
print("\namplitude distribution |am|+|pm|:", big.am_net.abs().add(big.pm_net.abs()).describe().round(2).to_dict())
# panels
panel=pd.read_csv("results/real_run_01/tables/station_selection.csv", dtype={"station_id":"string"})
sel=panel[panel.selected].station_id.tolist()
print("\npanel stations tide:")
t=tide.loc[tide.index.isin(sel),["am_net","pm_net","events","net","reversal"]].sort_values("events",ascending=False)
print(t.round(2).to_string())
print("\npanel reversal count:", int(t.reversal.sum()), "/", len(t))
# representative candidates
print("\n--- selection diagnostics ---")
print("max events:", tot.events.idxmax(), tot.events.max())
print("max net outflow among >=200:", big.net.idxmax(), big.net.max())
print("max net inflow among >=200:", big.net.idxmin(), big.net.min())
amp=(big.am_net.abs()+big.pm_net.abs())
print("max amplitude among >=200:", amp.idxmax(), round(amp.max(),2))
print("median events station:", tot.events.median())
print("balanced near-median station candidates:", tot[(tot.events.between(900,1200))&(tot.net.abs()<30)].head(8).round(0).to_string())
