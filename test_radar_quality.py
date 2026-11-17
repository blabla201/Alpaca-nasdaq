import unittest
import pandas as pd
import numpy as np
from radar_quality import assess, completed_bars, evaluate_horizons, session_state

class QualityTests(unittest.TestCase):
    def setUp(self):
        self.idx=pd.date_range('2026-11-17 09:30',periods=65,freq='min',tz='America/New_York')
        self.df=pd.DataFrame({'open':1.0,'high':1.01,'low':.99,'close':1.0,'volume':100.0,'ema9':.98,'vwap':.98},index=self.idx)
    def test_incomplete_excluded(self):
        now=pd.Timestamp('2026-11-17 10:34:30',tz='America/New_York')
        self.assertEqual(len(completed_bars(self.df,now)),64)
    def test_no_quote_never_tradable(self):
        now=pd.Timestamp('2026-11-17 10:35:05',tz='America/New_York')
        self.df.loc[self.idx[-1],'close']=1.015
        self.df.loc[self.idx[-1],'volume']=300
        r=assess(self.df,now)
        self.assertNotIn(r['Karar'],('KIRILIM ADAYI / SANAL','DİRENÇ YAKIN / SANAL'))
    def test_spread_blocks(self):
        now=pd.Timestamp('2026-11-17 10:35:05',tz='America/New_York')
        self.df.loc[self.idx[-1],'close']=1.015
        self.df.loc[self.idx[-1],'volume']=300
        r=assess(self.df,now,{'bid':1.0,'ask':1.04})
        self.assertIn('Spread çok yüksek',r['Neden'])
    def test_exact_horizon_only(self):
        rec=[{'Hisse':'XYZ','Sinyal mumu':str(self.idx[60]),'Fiyat':1.0}]
        d=self.df.loc[[self.idx[61],self.idx[65-1]]].copy()
        d.loc[self.idx[61],'close']=1.1
        out=evaluate_horizons(rec,{'XYZ':d})[0]
        self.assertAlmostEqual(out['1dk %'],10)
        self.assertIsNone(out['5dk %'])
    def test_weekend(self):
        self.assertEqual(session_state(pd.Timestamp('2026-11-21 10:00',tz='America/New_York')),'HAFTA SONU')
if __name__=='__main__': unittest.main()
