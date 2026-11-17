"""Auditable Alpaca screener discovery. Read-only; never submits orders."""
from datetime import datetime, timezone
import re
import requests

SCREENER = 'https://data.alpaca.markets/v1beta1/screener/stocks'
ASSETS = 'https://paper-api.alpaca.markets/v2/assets'
EXCLUDED = re.compile(r'\b(warrants?|units?|rights?|preferred|depositary shares?|notes?|bonds?)\b', re.I)

def ordinary_equity(asset):
    """Fail closed when classification metadata is unavailable."""
    if not isinstance(asset, dict):
        return False
    name = asset.get('name') or ''
    return (asset.get('class') == 'us_equity' and asset.get('status') == 'active'
            and asset.get('tradable') is True and asset.get('exchange') in {'NASDAQ','NYSE','AMEX','ARCA','BATS'}
            and bool(name.strip()) and not EXCLUDED.search(name))

def fetch_asset_map(key, secret, timeout=12, get=requests.get):
    headers={'APCA-API-KEY-ID':key,'APCA-API-SECRET-KEY':secret}
    r=get(ASSETS,headers=headers,params={'status':'active','asset_class':'us_equity'},timeout=timeout)
    r.raise_for_status()
    data=r.json()
    if not isinstance(data,list):
        raise ValueError('Asset response is not a list')
    return {a['symbol']:a for a in data if isinstance(a,dict) and a.get('symbol')}

def fetch_candidates(key,secret,limit=20,asset_map=None,timeout=12,get=requests.get):
    now=datetime.now(timezone.utc).isoformat(timespec='seconds')
    result={'symbols':[], 'details':[], 'errors':[], 'checked_at_utc':now,'rejected':[], 'source':'Alpaca screener movers + most-actives'}
    if not key or not secret:
        result['errors'].append('Alpaca API anahtarları eksik');return result
    headers={'APCA-API-KEY-ID':key,'APCA-API-SECRET-KEY':secret,'Cache-Control':'no-cache'}
    if asset_map is None:
        try: asset_map=fetch_asset_map(key,secret,timeout=timeout,get=get)
        except (requests.RequestException,ValueError,TypeError) as e:
            result['errors'].append(f'Menkul kıymet doğrulaması yapılamadı: {type(e).__name__}: {str(e)[:120]}')
            return result
    seen=set()
    for endpoint in ('movers','most-actives'):
        try:
            r=get(f'{SCREENER}/{endpoint}',headers=headers,timeout=timeout)
            r.raise_for_status(); data=r.json()
            if not isinstance(data,dict): raise ValueError('Invalid screener response')
            if endpoint=='movers':
                rows=[('Yükselenler',x) for x in data.get('gainers',[])] + [('Düşenler',x) for x in data.get('losers',[])]
            else: rows=[('En aktif',x) for x in data.get('most_actives',[])]
            for origin,item in rows:
                if not isinstance(item,dict): continue
                sym=item.get('symbol','')
                if not isinstance(sym,str) or not re.fullmatch(r'[A-Z]{1,5}',sym) or sym in seen: continue
                seen.add(sym)
                asset=asset_map.get(sym)
                if not ordinary_equity(asset):
                    result['rejected'].append({'Hisse':sym,'Neden':'Normal, aktif ve işlem yapılabilir hisse olarak doğrulanamadı'})
                    continue
                result['details'].append({'Hisse':sym,'Kaynak':origin,'Ad':asset['name'],'Borsa':asset['exchange']})
                result['symbols'].append(sym)
        except (requests.RequestException,ValueError,TypeError,AttributeError) as e:
            result['errors'].append(f'{endpoint}: {type(e).__name__}: {str(e)[:120]}')
    result['symbols']=result['symbols'][:limit]
    result['details']=result['details'][:limit]
    return result

def compare_scans(previous,current):
    old=set(previous or []); new=set(current or [])
    return {'new':sorted(new-old),'removed':sorted(old-new),'unchanged':sorted(new&old)}
