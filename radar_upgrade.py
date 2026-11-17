"""Independent, testable scan diagnostics. No order execution."""
from datetime import datetime, timezone
import math
import requests
import pandas as pd

SCREENER_BASE = 'https://data.alpaca.markets/v1beta1/screener/stocks'

def discover_symbols(key, secret, limit=20, timeout=7):
    """Alpaca movers/most-actives; discovery source may be delayed/incomplete."""
    if not key or not secret:
        return [], ['Alpaca API anahtarları yok']
    headers = {'APCA-API-KEY-ID': key, 'APCA-API-SECRET-KEY': secret}
    found, errors = [], []
    for endpoint in ('movers', 'most-actives'):
        try:
            r = requests.get(f'{SCREENER_BASE}/{endpoint}', headers=headers, timeout=timeout)
            r.raise_for_status()
            data = r.json()
            items = []
            if endpoint == 'movers':
                items = data.get('gainers', []) + data.get('losers', [])
            else:
                items = data.get('most_actives', [])
            for item in items:
                sym = item.get('symbol', '')
                if sym.isascii() and sym.isalpha() and 1 <= len(sym) <= 5 and sym not in found:
                    found.append(sym)
        except (requests.RequestException, ValueError, TypeError, AttributeError) as e:
            errors.append(f'{endpoint}: {type(e).__name__}: {str(e)[:130]}')
    return found[:limit], errors

def closed_bars(df, now=None):
    if df is None or df.empty:
        return df
    now = pd.Timestamp.now(tz='America/New_York') if now is None else pd.Timestamp(now).tz_convert('America/New_York')
    return df[df.index + pd.Timedelta(minutes=1) <= now]

def decision(df, now=None, max_age_minutes=3, max_extension_pct=1.2, min_rvol=1.3):
    """Return explainable observation, never a recommendation to buy."""
    if df is None or len(df) < 60:
        return {'Karar':'VERİ YETERSİZ', 'Neden':'60 kapanmış mum gerekli'}
    df = closed_bars(df, now)
    if len(df) < 60:
        return {'Karar':'VERİ YETERSİZ', 'Neden':'60 kapanmış mum gerekli'}
    now = pd.Timestamp.now(tz='America/New_York') if now is None else pd.Timestamp(now).tz_convert('America/New_York')
    last = df.iloc[-1]
    age = (now - (df.index[-1] + pd.Timedelta(minutes=1))).total_seconds()/60
    if age > max_age_minutes or age < 0:
        return {'Karar':'ESKİ VERİ', 'Neden':f'Son kapanmış mum {age:.1f} dk eski', 'Veri yaşı dk':round(age,1)}
    if (df.index[-1]-df.index[-2]).total_seconds() > 120:
        return {'Karar':'VERİ BOŞLUĞU', 'Neden':'Son iki mum arası 2 dakikadan fazla'}
    resistance = float(df.high.iloc[-21:-1].max())
    price = float(last.close)
    baseline = float(df.volume.iloc[-21:-1].mean())
    rvol = float(last.volume / baseline) if baseline > 0 else 0
    trend = price > float(last.vwap) and price > float(last.ema9)
    distance = 100*(price/resistance - 1) if resistance > 0 else float('nan')
    reasons=[]
    if not trend: reasons.append('VWAP/EMA9 teyidi yok')
    if rvol < min_rvol: reasons.append(f'Hacim {rvol:.2f}x, eşik {min_rvol:.2f}x')
    if distance > max_extension_pct: reasons.append(f'Dirençten %{distance:.2f} uzaklaştı; geç giriş riski')
    if distance < -0.8: reasons.append('Dirence henüz uzak')
    if not reasons and distance >= 0.1: status='KIRILIM İZLE / SANAL'
    elif not reasons and -0.8 <= distance < 0.1: status='DİRENCE YAKIN / SANAL'
    else: status='İŞLEM YAPMA / İZLE'
    return {'Karar':status,'Neden':'; '.join(reasons) or 'Trend, hacim ve direnç mesafesi uygun; spread teyidi YOK',
            'Fiyat':round(price,4),'Direnç':round(resistance,4),'Direnç uzaklık %':round(distance,2),
            'Hacim x':round(rvol,2),'Veri yaşı dk':round(age,1), 'Spread kontrolü':'YOK — AL sinyali değil'}

def evaluate_snapshots(records, latest):
    """Evaluate only matured timestamps; price snapshots are NOT execution prices."""
    for rec in records:
        if rec.get('Durum') != 'BEKLİYOR' or rec['Hisse'] not in latest:
            continue
        when, price = latest[rec['Hisse']]
        elapsed = (when-rec['Zaman']).total_seconds()/60
        if elapsed >= 5:
            rec['5dk %'] = round((price/rec['Fiyat']-1)*100, 2)
            rec['Durum']='ÖLÇÜLDÜ (son gözlem)'
    return records
