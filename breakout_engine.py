"""Single-source, causal breakout classification for closed 1-minute regular-session bars.
No trade execution; signal states are observations, not buy recommendations.
"""
import math
import pandas as pd

WINDOW = 20

def classify_breakout(df, now=None, window=WINDOW, near_pct=0.75, min_volume_ratio=1.5, max_extension_pct=1.2):
    def result(state, reason, **fields):
        return {'Kırılım durumu': state, 'Kırılım gerekçesi': reason, **fields}
    if df is None or len(df) < window + 2:
        return result('VERİ YETERSİZ', 'En az 22 adet 1 dakikalık mum gerekli')
    bars = df.sort_index().copy()
    if bars.index.tz is None:
        return result('VERİ HATASI', 'Mum zamanları saat dilimi içermiyor')
    now = pd.Timestamp.now(tz='America/New_York') if now is None else pd.Timestamp(now)
    if now.tzinfo is None:
        return result('VERİ HATASI', 'Şimdiki zaman saat dilimi içermiyor')
    now = now.tz_convert('America/New_York')
    bars = bars[(bars.index + pd.Timedelta(minutes=1)) <= now]
    bars = bars.between_time('09:30', '15:59')
    if len(bars) < window + 2:
        return result('VERİ YETERSİZ', 'Yeterli kapanmış normal seans mumu yok')
    last_day = bars.index[-1].date()
    session = bars[bars.index.date == last_day]
    if len(session) < window + 2:
        return result('VERİ YETERSİZ', 'Aynı seansta en az 22 kapanmış mum gerekli')
    recent = session.iloc[-(window + 2):]
    if (recent.index.to_series().diff().dropna() > pd.Timedelta(minutes=2)).any():
        return result('VERİ BOŞLUĞU', 'Direnç penceresinde 2 dakikayı aşan veri boşluğu')
    last = session.iloc[-1]
    prev = session.iloc[-2]
    resistance = float(session.high.iloc[-(window + 1):-1].max())
    previous_resistance = float(session.high.iloc[-(window + 2):-2].max())
    price = float(last.close)
    prev_price = float(prev.close)
    if not all(math.isfinite(x) and x > 0 for x in (price, resistance, previous_resistance)):
        return result('VERİ HATASI', 'Fiyat veya direnç geçersiz')
    age = (now - (session.index[-1] + pd.Timedelta(minutes=1))).total_seconds() / 60
    if age > 3 or age < 0:
        return result('ESKİ VERİ', f'Son kapanmış mum {age:.1f} dakika eski', **{'Veri yaşı dk': round(age, 1)})
    vol_base = float(session.volume.iloc[-(window + 1):-1].mean())
    ratio = float(last.volume) / vol_base if vol_base > 0 else 0.0
    distance = (price / resistance - 1) * 100
    spread = float(last.high) - float(last.low)
    body_ratio = (price - float(last.open)) / spread if spread > 0 else 0.0
    # Avoid declaring an existing run-up a fresh crossing.
    crossed = prev_price <= previous_resistance and price > resistance
    # ATR used as a dynamic minimum buffer, bounded to avoid unreasonable thresholds.
    true_range = pd.concat([
        session.high - session.low,
        (session.high - session.close.shift(1)).abs(),
        (session.low - session.close.shift(1)).abs()
    ], axis=1).max(axis=1)
    atr = float(true_range.iloc[-15:-1].mean())
    buffer_pct = min(0.30, max(0.05, 0.10 * atr / resistance * 100)) if math.isfinite(atr) else 0.10
    base = {'Fiyat': round(price, 4), 'Direnç': round(resistance, 4),
            'Dirence uzaklık %': round(distance, 2), 'Hacim oranı': round(ratio, 2),
            'Kırılım tamponu %': round(buffer_pct, 3), 'Veri yaşı dk': round(age, 2)}
    if crossed and distance >= buffer_pct:
        if ratio >= min_volume_ratio and body_ratio >= 0.5:
            if distance > max_extension_pct:
                return result('GEÇ KIRILIM', 'Kırılım doğrulandı ancak dirençten çok uzaklaştı', **base)
            return result('TEYİTLİ KIRILIM', 'Yeni direnç geçişi, güçlü pozitif mum ve hacim teyidi', **base)
        return result('TEYİTSİZ GEÇİŞ', 'Direnç geçildi ancak hacim veya mum gövdesi teyidi eksik', **base)
    if price <= resistance and float(last.high) > resistance:
        return result('FİTİL / RED', 'Fiyat direnci test etti ancak üzerinde kapanmadı', **base)
    if distance > 0:
        return result('KIRILIM SONRASI', 'Fiyat direnç üstünde; bu mumda yeni geçiş doğrulanmadı', **base)
    if -near_pct <= distance <= 0:
        return result('DİRENCE YAKIN', 'Direnç henüz geçilmedi; yalnızca izleme', **base)
    return result('DİRENCE UZAK', 'Dirence yaklaşılmadı; kırılım sinyali yok', **base)
