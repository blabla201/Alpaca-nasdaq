import unittest
from discovery_engine import ordinary_equity,compare_scans,fetch_candidates

GOOD={'class':'us_equity','status':'active','tradable':True,'exchange':'NASDAQ','name':'Example Technologies Common Stock'}
class FakeResponse:
    def __init__(self,payload): self.payload=payload
    def raise_for_status(self): pass
    def json(self): return self.payload
class DiscoveryTests(unittest.TestCase):
    def test_common_stock(self): self.assertTrue(ordinary_equity(GOOD))
    def test_warrant_excluded(self): self.assertFalse(ordinary_equity({**GOOD,'name':'Example Warrants'}))
    def test_unit_excluded(self): self.assertFalse(ordinary_equity({**GOOD,'name':'Example Units'}))
    def test_missing_metadata_excluded(self): self.assertFalse(ordinary_equity(None))
    def test_inactive_excluded(self): self.assertFalse(ordinary_equity({**GOOD,'status':'inactive'}))
    def test_comparison(self): self.assertEqual(compare_scans(['A','B'],['B','C']),{'new':['C'],'removed':['A'],'unchanged':['B']})
    def test_discovery_filters_and_deduplicates(self):
        def fake(url,**kw):
            return FakeResponse({'gainers':[{'symbol':'GOOD'},{'symbol':'WARR'}],'losers':[]} if url.endswith('movers') else {'most_actives':[{'symbol':'GOOD'},{'symbol':'NEXT'}]})
        r=fetch_candidates('k','s',asset_map={'GOOD':GOOD,'WARR':{**GOOD,'name':'Example Warrant'},'NEXT':GOOD},get=fake)
        self.assertEqual(r['symbols'],['GOOD','NEXT'])
        self.assertEqual(len(r['rejected']),1)
    def test_failed_validation_no_unverified_symbols(self):
        def broken(*args,**kwargs): raise ValueError('bad response')
        r=fetch_candidates('k','s',get=broken)
        self.assertEqual(r['symbols'],[])
        self.assertTrue(r['errors'])
if __name__=='__main__':unittest.main()
