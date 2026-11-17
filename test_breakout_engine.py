import unittest
import numpy as np
import pandas as pd
from breakout_engine import classify_breakout

class BreakoutTests(unittest.TestCase):
    def bars(self, last_close=9.99, last_high=None, last_open=None, last_vol=100, prev_close=9.9):
        idx = pd.date_range('2026-11-17 09:30', periods=45, freq='min', tz='America/New_York')
        d = pd.DataFrame({'open':np.full(45,9.9), 'high':np.full(45,10.0),
                          'low':np.full(45,9.8), 'close':np.full(45,9.9),
                          'volume':np.full(45,100)}, index=idx)
        d.iloc[-2,d.columns.get_loc('close')] = prev_close
        d.iloc[-1,d.columns.get_loc('close')] = last_close
        d.iloc[-1,d.columns.get_loc('open')] = last_open if last_open is not None else 9.85
        d.iloc[-1,d.columns.get_loc('high')] = last_high if last_high is not None else max(10.0,last_close)
        d.iloc[-1,d.columns.get_loc('volume')] = last_vol
        return d
    def run_case(self, **kw):
        return classify_breakout(self.bars(**kw), pd.Timestamp('2026-11-17 10:15',tz='America/New_York'))
    def test_far(self):
        self.assertEqual(self.run_case(last_close=9.0)['Kırılım durumu'], 'DİRENCE UZAK')
    def test_near(self):
        self.assertEqual(self.run_case(last_close=9.97)['Kırılım durumu'], 'DİRENCE YAKIN')
    def test_wick(self):
        self.assertEqual(self.run_case(last_close=9.95,last_high=10.2)['Kırılım durumu'], 'FİTİL / RED')
    def test_confirmed(self):
        self.assertEqual(self.run_case(last_close=10.06,last_high=10.08,last_vol=250)['Kırılım durumu'], 'TEYİTLİ KIRILIM')
    def test_no_volume(self):
        self.assertEqual(self.run_case(last_close=10.06,last_high=10.08,last_vol=100)['Kırılım durumu'], 'TEYİTSİZ GEÇİŞ')
    def test_late(self):
        self.assertEqual(self.run_case(last_close=10.2,last_high=10.22,last_vol=250)['Kırılım durumu'], 'GEÇ KIRILIM')
    def test_already_above(self):
        self.assertEqual(self.run_case(last_close=10.06,last_high=10.08,last_vol=250,prev_close=10.05)['Kırılım durumu'], 'KIRILIM SONRASI')
    def test_old(self):
        self.assertEqual(classify_breakout(self.bars(),pd.Timestamp('2026-11-17 11:15',tz='America/New_York'))['Kırılım durumu'], 'ESKİ VERİ')
    def test_no_future_candle(self):
        self.assertEqual(classify_breakout(self.bars(),pd.Timestamp('2026-11-17 10:14:30',tz='America/New_York'))['Kırılım durumu'], 'DİRENCE UZAK')

if __name__=='__main__': unittest.main()
