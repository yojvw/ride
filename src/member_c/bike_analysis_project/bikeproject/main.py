import argparse
import logging
import json
from pathlib import Path
import pandas as pd
from .io import read_config,load_inputs,save_json,reproducibility
from .panel import build_panel,make_features,feature_columns
from .analysis import analyse
from .forecast import run_forecast
from .evaluation import tables
from .simulation import run_simulations
from .plots import make_plots


def run(config_path,overwrite=False):
    cfg=read_config(config_path)
    out=Path(cfg['output_dir'])
    if out.exists() and any(out.iterdir()) and not overwrite:
        raise FileExistsError(f'Nonempty output directory: {out}; use a new path or --overwrite.')
    if out.exists() and overwrite:
        import shutil
        protected=[Path(cfg[k]).resolve() for k in ['rides_path','coverage_path','stations_path'] if cfg.get(k)]
        if any(out.resolve()==p or out.resolve() in p.parents for p in protected) or out.resolve()==Path.cwd().resolve():
            raise ValueError('Unsafe output path: would contain input files or the project root.')
        if not (out/'.bikeproject-output').exists():
            raise ValueError('Refusing overwrite: directory was not marked as a bikeproject output.')
        shutil.rmtree(out)
    out.mkdir(parents=True,exist_ok=True)
    (out/'.bikeproject-output').write_text('Generated experiment outputs only.\n',encoding='utf-8')
    for part in ['tables','figures']: (out/part).mkdir()
    log=logging.getLogger('bikeproject');log.setLevel(logging.INFO)
    handler=logging.FileHandler(out/'run.log',encoding='utf-8');log.addHandler(handler)
    try:
        log.info('Starting input validation')
        rides,coverage,stations,audit=load_inputs(cfg)
        save_json(audit,out/'input_audit.json');save_json(reproducibility(cfg),out/'manifest.json')
        log.info('Building panel and leakage-safe historical features')
        panel,selection=build_panel(rides,coverage,cfg)
        panel.to_csv(out/'tables/hourly_panel.csv',index=False)
        selection.to_csv(out/'tables/station_selection.csv',index=False)
        features=make_features(panel)
        features.to_csv(out/'tables/features.csv',index=False)
        eligibility=[]
        for target in ['departures','arrivals']:
            valid=features[[target]+feature_columns(target)].notna().all(axis=1)
            eligibility.append({'target':target,'total_panel_rows':len(features),'eligible_rows':int(valid.sum()),
                                'excluded_rows':int((~valid).sum())})
        save_json(eligibility,out/'model_eligibility.json')
        eda=analyse(rides,panel,stations,cfg,out/'tables')
        log.info('Running rolling validation, ablations and final test')
        pred,chosen=run_forecast(features,cfg)
        pred.to_csv(out/'tables/predictions.csv',index=False)
        metrics,station_metrics,hour_metrics,worst=tables(pred)
        for name,frame in [('metrics',metrics),('station_metrics',station_metrics),('hour_metrics',hour_metrics),('worst_errors',worst)]:
            frame.to_csv(out/f'tables/{name}.csv',index=False)
        save_json(chosen,out/'validation_selected_models.json')
        log.info('Running assumption-based simulation')
        sim=run_simulations(rides,pred,stations,panel,cfg,out/'tables')
        if not sim.empty: sim.to_csv(out/'tables/simulation_summary.csv',index=False)
        make_plots(eda,pred,metrics,sim,out/'figures',cfg)
        lines=['# Run summary','',f"Synthetic demonstration: {cfg.get('synthetic_demo',False)}",'',
               f"Input rows: {len(rides)}; selected stations: {panel.station_id.nunique()}",
               f"Input clock convention: {cfg['time_basis']}",'',
               '## Validation-selected model results','',
               '| Target | Selected on validation | Test MAE | Test RMSE |','|---|---|---:|---:|']
        for target,model in chosen.items():
            r=metrics[(metrics.split=='test')&(metrics.target==target)&(metrics.model==model)].iloc[0]
            lines.append(f'| {target} | {model} | {r.mae:.4f} | {r.rmse:.4f} |')
        lines+=['','## Boundaries','',
                '- Forecasts are rolling one-hour-ahead predictions, NOT a day-ahead plan.',
                '- Candidates and simulation policies are fixed; the chosen model uses validation MAE only.',
                '- All model comparisons use the same complete-feature rows; warm-up/gap exclusions are logged.',
                '- Cohort selection uses data before the earliest rolling-validation window.',
                '- Nominal 90% intervals have no guaranteed coverage; see empirical coverage and width.',
                '- Coverage assumptions must be audited. Calendar-normalized overall counts are descriptive, not corrected demand.',
                '- Simulation uses assumed capacity/inventory and observed trips as fixed requests.',
                '- Hourly moves are instantaneous, bikes are pooled, and bike-km is only a cost proxy.',
                '- Overflow bikes remain in a holding pool and are not automatically recirculated.',
                '- Boundary arrivals/departures are explicitly logged; no actual unmet demand or financial savings are inferred.',
                '- A single month cannot establish annual seasonality or generalization to other cities.']
        (out/'RUN_SUMMARY.md').write_text('\n'.join(lines),encoding='utf-8')
        log.info('Completed successfully')
        return {'input_rows':len(rides),'stations':panel.station_id.nunique(),'prediction_rows':len(pred),
                'figures':len(list((out/'figures').glob('*.png'))),'output_dir':str(out)}
    except Exception:
        log.exception('Run failed');raise
    finally:
        log.removeHandler(handler);handler.close()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--config',required=True)
    parser.add_argument('--overwrite',action='store_true')
    args=parser.parse_args()
    print(json.dumps(run(args.config,args.overwrite),ensure_ascii=False,indent=2))

if __name__=='__main__': main()
