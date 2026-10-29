import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
import pandas as pd
from .engine import Adapter,config_read,save_json,resolve,tuning_predictions,compare_reference,fold_predictions
from .metrics import summarize,choose,paired_bootstrap,metrics
from .state import append_ledger,reserve_test,write_lock,read_lock


def figure(summary,out,title):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(12,4))
    for ax,target in zip(axes,['departures','arrivals']):
        g=summary[summary.target==target]
        ax.barh(g.model,g.mae);ax.set_title(target);ax.set_xlabel('MAE')
    fig.suptitle(title+' | rolling one-hour-ahead, NOT day-ahead');fig.tight_layout(rect=[0,0,1,.9])
    fig.savefig(out,dpi=150);plt.close(fig)


def tune(config_path,project_root):
    project_root=Path(project_root).resolve();protocol=config_read(config_path)
    run_id=protocol['run_id']
    if not re.fullmatch(r'[A-Za-z0-9_-]+',run_id):raise ValueError('Unsafe run_id')
    ledger=resolve(project_root,protocol.get('ledger_dir','experiments'))
    out=ledger/run_id
    if out.exists():raise FileExistsError(f'Use a new run_id; refusing to overwrite {out}')
    out.mkdir(parents=True)
    append_ledger(ledger,{'run_id':run_id,'phase':'tune','status':'started','details':'validation/CV only'})
    try:
        adapter=Adapter(project_root,protocol)
        pred,extra=tuning_predictions(adapter)
        reproduction=compare_reference(adapter,pred)
        summary=summarize(pred)
        chosen,paired,decisions=choose(pred,summary,protocol)
        pred.to_csv(out/'validation_cv_predictions.csv',index=False)
        summary.to_csv(out/'validation_cv_metrics.csv',index=False)
        paired.to_csv(out/'validation_paired_bootstrap.csv',index=False)
        decisions.to_csv(out/'selection_decisions.csv',index=False)
        save_json(reproduction,out/'baseline_reproduction.json')
        save_json({'baseline_feature_count':len(adapter.original_columns),'adaptive_added_count':len(extra),
                   'original_columns':adapter.original_columns,'extra_columns':extra,
                   'eligibility':'exactly_original_full_feature_mask','new_168h_warmup':False},out/'feature_audit.json')
        lock={'version':'0.2.0','run_id':run_id,'protocol':protocol,'fingerprint':adapter.meta,
              'chosen':chosen,'specs':adapter.specs,'baseline_columns':adapter.original_columns,'extra_columns':extra,
              'baseline_reproduction':reproduction,'test_status':'not_scored_during_tune'}
        write_lock(lock,out)
        vals=summary[summary.split=='validation']
        prefix='SYNTHETIC DEMO ' if adapter.demo else ''
        figure(vals,out/'validation_comparison.png',prefix+'Validation candidates')
        lines=['# 算法优化：验证阶段','',f'虚构演示：{adapter.demo}',
               '测试期未评分；此处所有模型选择只使用验证集与训练期滚动CV。','',
               '| 目标 | 保留方案 | 验证MAE | 原模型验证MAE |','|---|---|---:|---:|']
        for target,name in chosen.items():
            r=vals[(vals.target==target)&(vals.model==name)].iloc[0]
            b=vals[(vals.target==target)&(vals.model=='hgb_full')].iloc[0]
            lines.append(f'| {target} | {name} | {r.mae:.6f} | {b.mae:.6f} |')
        lines+=['','## 解读规则','',
                '- 默认要求验证MAE改善、日块配对区间上界<0、CV不过度退步，并且峰值MAE和欠预测率不恶化。',
                '- 不满足筛选条件时保留原hgb_full；增加模型不保证提升。',
                '- 区间只有少量日块，且同一验证集用于筛选；不是多重比较修正后的显著性证明。',
                '- 峰值按实际需求筛选，欠预测率高不单独证明模型有可修正偏差。',
                '- MAE导向模型预测条件中位数；不应自动替代调度所需的期望需求。',
                '- 已看过旧测试报告，因此之后测试是已知测试期上的探索性复核，不是全新盲测。',
                '- 不读取未来气象、不加入目标小时会员数量、不伪造库存。',
                '- 请查selection_decisions.csv了解为什么接受或拒绝候选；不调整门槛追求漂亮结果。']
        (out/'OPTIMIZATION_REPORT.md').write_text('\n'.join(lines),encoding='utf-8')
        append_ledger(ledger,{'run_id':run_id,'phase':'tune','status':'locked','details':json.dumps(chosen)})
        return {'run_id':run_id,'chosen':chosen,'test_scored':False,'result_directory':str(out)}
    except Exception as exc:
        save_json({'error':repr(exc),'test_scored':False},out/'FAILED.json')
        append_ledger(ledger,{'run_id':run_id,'phase':'tune','status':'failed','details':repr(exc)})
        raise


def finalize(run_directory,project_root,acknowledge=False):
    if not acknowledge:raise ValueError('Require --acknowledge-used-test; this is not an untouched test set.')
    project_root=Path(project_root).resolve();run_directory=Path(run_directory).resolve()
    lock=read_lock(run_directory);protocol=lock['protocol']
    adapter=Adapter(project_root,protocol)
    if adapter.meta!=lock['fingerprint']:raise ValueError('Inputs/source/environment/config changed after lock; refuse final test.')
    if adapter.specs!=lock['specs']:raise ValueError('Candidate registry changed after lock')
    ledger=resolve(project_root,protocol.get('ledger_dir','experiments'))
    final=run_directory/'final_test'
    if final.exists():raise FileExistsError('Final test already attempted for this run; do not repeat.')
    data_digest=hashlib.sha256(json.dumps(adapter.meta['inputs'],sort_keys=True).encode()).hexdigest()
    budget=reserve_test(ledger,lock['run_id'],protocol.get('test_evaluations_already_used',1),
                        protocol.get('maximum_total_test_evaluations',3),data_digest)
    final.mkdir()
    save_json(budget,final/'test_budget_reservation.json')
    append_ledger(ledger,{'run_id':lock['run_id'],'phase':'final_test','status':'reserved','details':f"budget used={budget['used']}"})
    try:
        features,extra=adapter.frame(True)
        if extra!=lock['extra_columns']:raise ValueError('Feature list changed')
        names={t:list(dict.fromkeys(['hgb_full',lock['chosen'][t]])) for t in ['departures','arrivals']}
        pred=fold_predictions(adapter,features,extra,'test',pd.Timestamp(adapter.hostcfg['validation_end']),
                              pd.Timestamp(adapter.hostcfg['analysis_end']),names,
                              protocol.get('final_prediction_intervals',True))
        summary=summarize(pred)
        pairs=[]
        for target,name in lock['chosen'].items():
            g=pred[pred.target==target]
            pairs.append({'target':target,'selected_model':name,**paired_bootstrap(g[g.model==name],g[g.model=='hgb_full'],
                                         protocol.get('bootstrap_repetitions',2000),protocol.get('seed',42))})
        pred.to_csv(final/'predictions.csv',index=False);summary.to_csv(final/'metrics.csv',index=False)
        pd.DataFrame(pairs).to_csv(final/'paired_bootstrap.csv',index=False)
        by_station=[];by_hour=[]
        for (target,model),g in pred.groupby(['target','model']):
            for sid,sub in g.groupby('station_id'):by_station.append({'target':target,'model':model,'station_id':sid,**metrics(sub)})
            for hour,sub in g.groupby(g.time.dt.hour):by_hour.append({'target':target,'model':model,'hour':hour,**metrics(sub)})
        pd.DataFrame(by_station).to_csv(final/'station_metrics.csv',index=False)
        pd.DataFrame(by_hour).to_csv(final/'hour_metrics.csv',index=False)
        figure(summary,final/'final_comparison.png',('SYNTHETIC DEMO ' if adapter.demo else '')+'Locked candidates on previously inspected test period')
        lines=['# 锁定方案的测试复核','',
               '注意：此前已查看该测试期诊断，本次为探索性复核，不能称全新独立盲测。',
               f"测试预算已使用：{budget['used']} / {budget['maximum']}（包含交接报告记载的历史使用次数）。",'',
               '| 目标 | 模型 | MAE | RMSE | 峰值MAE |','|---|---|---:|---:|---:|']
        for r in summary.itertuples():lines.append(f'| {r.target} | {r.model} | {r.mae:.6f} | {r.rmse:.6f} | {r.peak_mae:.6f} |')
        lines+=['','选择已在测试前锁定；不得按本表结果重新挑选模型或调整阈值。',
                '区间为辅助分位数模型，没有保序校准或时间序列覆盖保证。',
                '不会覆盖旧predictions.csv，也不会自动将MAE最优中位数预测送入原调度模块。']
        (final/'FINAL_REPORT.md').write_text('\n'.join(lines),encoding='utf-8')
        append_ledger(ledger,{'run_id':lock['run_id'],'phase':'final_test','status':'completed','details':'No reselection'})
        return {'final_directory':str(final),'test_budget_used':budget['used'],'selected_before_test':lock['chosen']}
    except Exception as exc:
        save_json({'error':repr(exc),'budget_is_consumed':True},final/'FAILED.json')
        append_ledger(ledger,{'run_id':lock['run_id'],'phase':'final_test','status':'failed','details':repr(exc)})
        raise


def main():
    p=argparse.ArgumentParser(description='Incremental bike forecasting optimization; never modifies original code or cleaned data.')
    sub=p.add_subparsers(dest='command',required=True)
    t=sub.add_parser('tune');t.add_argument('--config',required=True);t.add_argument('--project-root',default='.')
    f=sub.add_parser('finalize');f.add_argument('--run',required=True);f.add_argument('--project-root',default='.')
    f.add_argument('--acknowledge-used-test',action='store_true')
    a=p.parse_args();sys.path.insert(0,str(Path(a.project_root).resolve()))
    result=tune(a.config,a.project_root) if a.command=='tune' else finalize(a.run,a.project_root,a.acknowledge_used_test)
    print(json.dumps(result,ensure_ascii=False,indent=2))
