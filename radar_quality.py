"""Conservative 1-minute observation engine; no order placement or profit forecast."""
from datetime import time
import math
import pandas as pd
import requests

NY = 'America/New_York'
HORIZONS = (1, 5, 10, 30)

def session_state(now=None):
    now = pd.Timestamp.now(tz=NY) if now is None else pd.Timestamp(now).tz_convert(NY)
    if now.weekday() >= 5:
        return 'HAFTA SONU'
    clock = now.time()
    if time(4) <= clock < time(9,30): return 'PRE-MARKET'
    if time(9,30) <= clock < time(16): return 'NORMAL SEANS'
    if time(16) <= clock < time(20): return 'AFTER-HOURS'
    return 'KAPALI'

def completed_bars(df, now=None):
    if df is None or df.empty: return df
    now = pd.Timestamp.now(tz=NY) if now is None else pd.Timestamp(now).tz_convert(NY)
    return df[df.index + pd.Timedelta(minutes=1) <= now].copy()

def assess(df, now=None, quote=None, max_spread_pct=0.65):
    """Quote is optional dict with bid/ask; no quote => never a tradable signal."""
    now = pd.Timestamp.now(tz=NY) if now is None else pd.Timestamp(now).tz_convert(NY)
    state = session_state(now)
    out = {'Karar':'İŞLEM YAPMA', 'Seans':state, 'Neden':'', 'Spread %':None}
    if state != 'NORMAL SEANS':
        out['Neden']='Normal seans dışında; premarket ayrı izlenmeli'
        return out
    d = completed_bars(df, now)
    if d is None or len(d) < 60:
        out['Neden']='60 kapanmış mum yok'
        return out
    age = (now-(d.index[-1]+pd.Timedelta(minutes=1))).total_seconds()/60
    out['Veri yaşı dk']=round(age,2)
    if age < 0 or age > 2:
        out['Neden']='Eski/gelecek tarihli mum'
        return out
    if (d.index[-1]-d.index[-2]).total_seconds() > 60:
        out['Neden']='Son mumlarda boşluk var (IEX düşük likidite veya veri eksikliği)'
        return out
    last = d.iloc[-1]
    resistance = float(d.high.iloc[-21:-1].max())
    px = float(last.close)
    volbase = float(d.volume.iloc[-21:-1].mean())
    if resistance <= 0 or px <= 0 or volbase <= 0:
        out['Neden']='Geçersiz fiyat/hacim'
        return out
    rvol = float(last.volume)/volbase
    extension = (px/resistance-1)*100
    out.update({'Fiyat':round(px,4),'Direnç':round(resistance,4), 'Direnç uzaklık %':round(extension,2), 'Hacim x':round(rvol,2)})
    issues=[]
    if not (px > float(last.ema9) and px > float(last.vwap)):
        issues.append('EMA9/VWAP teyidi yok')
    if rvol < 1.5: issues.append('Göreceli hacim yetersiz (IEX)')
    if extension > 1.0: issues.append('Dirençten uzak; geç giriş')
    if extension < -0.75: issues.append('Dirence uzak')
    if quote is None:
        issues.append('Güncel bid/ask yok; işlem yapılabilirlik bilinmiyor')
    else:
        try:
            bid, ask = float(quote['bid']), float(quote['ask'])
            spread = 100*(ask-bid)/((ask+bid)/2)
            if not (0 < bid <= ask and math.isfinite(spread)):
                issues.append('Geçersiz bid/ask')
            else:
                out['Spread %']=round(spread,3)
                if spread > max_spread_pct: issues.append('Spread çok yüksek')
        except (ValueError, TypeError, KeyError):
            issues.append('Bid/ask okunamadı')
    if issues:
        out['Neden']='; '.join(issues)
        out['Karar']='İZLE — GİRİŞ YOK' if -0.75 <= extension <= 1.0 else 'İŞLEM YAPMA'
    elif extension >= 0.1:
        out['Karar']='KIRILIM ADAYI / SANAL'
        out['Neden']='Kapanmış mum + hacim + trend + spread koşulları sağlandı; kâr garantisi yok'
    else:
        out['Karar']='DİRENÇ YAKIN / SANAL'
        out['Neden']='Henüz kırılım teyidi yok'
    return out

def quote_iex(key, secret, symbols, timeout=8):
    """Alpaca latest IEX quotes; errors are visible to caller."""
    if not key or not secret: return {}, 'API anahtarları eksik'
    if not symbols: return {}, None
    url='https://data.alpaca.markets/v2/stocks/quotes/latest'
    try:
        response=requests.get(url, params={'symbols':','.join(symbols),'feed':'iex'},
                              headers={'APCA-API-KEY-ID':key,'APCA-API-SECRET-KEY':secret},timeout=timeout)
        response.raise_for_status()
        quotes={}
        for sym,q in response.json().get('quotes',{}).items():
            if q.get('bp') is not None and q.get('ap') is not None:
                quotes[sym]={'bid':q['bp'],'ask':q['ap'],'timestamp':q.get('t')}
        return quotes,None
    except (requests.RequestException,ValueError,TypeError,AttributeError) as exc:
        return {},f'{type(exc).__name__}: {str(exc)[:160]}'

def evaluate_horizons(records, bars_by_symbol):
    """Exact minute horizons; do not substitute later last price for missing target bar."""
    updated=[]
    for record in records:
        r=dict(record)
        sym=r['Hisse']
        df=bars_by_symbol.get(sym)
        if df is None or df.empty:
            updated.append(r); continue
        stamp=pd.Timestamp(r['Sinyal mumu'])
        if stamp.tzinfo is None: stamp=stamp.tz_localize(NY)
        else: stamp=stamp.tz_convert(NY)
        for minutes in HORIZONS:
            col=f'{minutes}dk %'
            target=stamp+pd.Timedelta(minutes=minutes)
            if target in df.index:
                px=float(df.loc[target,'close'])
                r[col]=round((px/float(r['Fiyat'])-1)*100,3)
            elif col not in r:
                r[col]=None
        updated.append(r)
    return updated
