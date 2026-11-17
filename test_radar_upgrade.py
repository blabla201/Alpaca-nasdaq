import unittest
import pandas as pd
import numpy as np
from radar_upgrade import decision, closed_bars, evaluate_snapshots

class RadarUpgradeTests(unittest.TestCase):
    def make_df(self):
        idx=pd.date_range('2026-11-17 10:00',periods=70,freq='min',tz='America/New_York')
        df=pd.DataFrame({'open':np.ones(70),'high':np.ones(70)*1.01,'low':np.ones(70)*.99,'close':np.ones(70),'volume':np.ones(70)*100,'vwap':np.ones(70)*.98,'ema9':np.ones(70)*.99},index=idx)
        return df
    def test_incomplete_bar_removed(self):
        df=self.make_df()
        out=closed_bars(df,pd.Timestamp('2026-11-17 11:09:30',tz='America/New_York'))
        self.assertEqual(len(out),69)
    def test_stale_data_rejected(self):
        df=self.make_df()
        r=decision(df,pd.Timestamp('2026-11-17 12:00',tz='America/New_York'))
        self.assertEqual(r['Karar'],'ESKİ VERİ')
    def test_low_volume_rejected(self):
        df=self.make_df()
        r=decision(df,pd.Timestamp('2026-11-17 11:10',tz='America/New_York'))
        self.assertIn('Hacim',r['Neden'])
    def test_matured_signal_only(self):
        stamp=pd.Timestamp('2026-11-17 10:00',tz='America/New_York')
        rec=[{'Hisse':'XYZ','Zaman':stamp,'Fiyat':1,'Durum':'BEKLİYOR'}]
        evaluate_snapshots(rec,{'XYZ':(stamp+pd.Timedelta(minutes=4),1.1)})
        self.assertEqual(rec[0]['Durum'],'BEKLİYOR')
        evaluate_snapshots(rec,{'XYZ':(stamp+pd.Timedelta(minutes=5),1.1)})
        self.assertEqual(rec[0]['5dk %'],10.0)
if __name__=='__main__':unittest.main()
