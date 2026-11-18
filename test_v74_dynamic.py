import unittest
from unittest.mock import Mock
from unittest.mock import patch
import auto_alert_worker as w

class DynamicDiscoveryTests(unittest.TestCase):
    @patch.object(w, 'fetch_candidates', return_value={'symbols':['FRTT','ABCD','GP'], 'errors':[]})
    @patch.object(w, 'fetch_asset_map', return_value={'FRTT':{},'ABCD':{},'GP':{}})
    @patch.object(w, 'symbols_from_env', return_value=['RIOT','FRTT'])
    def test_merge_deduplicates(self, fixed, assets, candidates):
        self.assertEqual(w.build_universe(Mock(),'key','secret'), ['RIOT','FRTT','ABCD','GP'])
    @patch.object(w, 'fetch_asset_map', side_effect=ValueError('api'))
    @patch.object(w, 'symbols_from_env', return_value=['RIOT','SNAP'])
    def test_fallback(self, fixed, assets):
        self.assertEqual(w.build_universe(Mock(),'key','secret'), ['RIOT','SNAP'])
    @patch.object(w, 'fetch_candidates', return_value={'symbols':[f'X{i}' for i in range(30)], 'errors':[]})
    @patch.object(w, 'fetch_asset_map', return_value={})
    @patch.object(w, 'symbols_from_env', return_value=['RIOT','SNAP'])
    def test_total_cap(self, fixed, assets, candidates):
        self.assertEqual(len(w.build_universe(Mock(),'key','secret')), 22)

if __name__ == '__main__': unittest.main()
