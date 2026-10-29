from contextlib import contextmanager
from datetime import datetime,timezone
from pathlib import Path
import csv
import json
import os
from .engine import save_json,config_read,digest

@contextmanager
def exclusive(path):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    os.close(fd)
    try:yield
    finally:path.unlink(missing_ok=True)


def utcnow():return datetime.now(timezone.utc).isoformat()


def append_ledger(directory,row):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    path=directory/'optimization_ledger.csv'
    fields=['time','run_id','phase','status','details']
    with exclusive(directory/'.ledger.lock'):
        exists=path.exists()
        with path.open('a',newline='',encoding='utf-8-sig') as f:
            w=csv.DictWriter(f,fieldnames=fields)
            if not exists:w.writeheader()
            w.writerow({'time':utcnow(),**row})


def reserve_test(directory,run_id,initial_used,maximum,dataset_digest):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    path=directory/'optimization_test_budget.json'
    with exclusive(directory/'.test_budget.lock'):
        if path.exists():
            state=config_read(path)
            if state['dataset_digest']!=dataset_digest:raise ValueError('Budget belongs to another dataset')
            if state['maximum']!=maximum:raise ValueError('Changing maximum test budget is not allowed')
        else:state={'used':initial_used,'maximum':maximum,'dataset_digest':dataset_digest,'reservations':[]}
        if any(r['run_id']==run_id for r in state['reservations']):raise ValueError('This run already reserved a final test')
        if state['used']>=state['maximum']:raise ValueError('Test budget exhausted')
        state['used']+=1
        state['reservations'].append({'run_id':run_id,'time':utcnow(),'status':'reserved_even_if_run_fails'})
        temp=path.with_suffix('.tmp');save_json(state,temp);os.replace(temp,path)
    return state


def write_lock(payload,directory):
    directory=Path(directory);p=directory/'LOCK.json';save_json(payload,p)
    (directory/'LOCK.sha256').write_text(digest(p),encoding='utf-8')


def read_lock(directory):
    directory=Path(directory);p=directory/'LOCK.json'
    expected=(directory/'LOCK.sha256').read_text().strip()
    if digest(p)!=expected:raise ValueError('LOCK.json changed after tuning')
    return config_read(p)
