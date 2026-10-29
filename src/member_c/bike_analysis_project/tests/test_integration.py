import unittest
import tempfile
import json
from pathlib import Path
import pandas as pd
from scripts.make_demo import make_demo
from bikeproject.main import run

class IntegrationTest(unittest.TestCase):
    def test_synthetic_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            make_demo(p)
            cfg=json.loads((p/'config.json').read_text())
            cfg['max_iter']=8
            cfg['rolling_folds']=0
            cfg['prediction_intervals']=False
            cfg['simulation']['enabled']=False
            (p/'config.json').write_text(json.dumps(cfg))
            result=run(p/'config.json')
            self.assertEqual(result['stations'],4)
            self.assertTrue((p/'results/RUN_SUMMARY.md').exists())
            self.assertEqual(result['figures'],7)
            pred=pd.read_csv(p/'results/tables/predictions.csv')
            self.assertTrue((pred.prediction>=0).all())
            for _,g in pred.groupby(['split','target']):
                counts=g.groupby('model').size()
                self.assertEqual(counts.nunique(),1)

if __name__=='__main__': unittest.main()
