"""
Lab Nasdaq Bot - tek dosya (app.py)
- iPhone'da Streamlit uygulaması olarak çalışır
- Aynı dosya GitHub Actions'ta arka plan botu olarak da çalışır:  python app.py --worker
Yalnızca analiz ve sanal test. Otomatik emirler kapalıdır.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
from radar_upgrade import discover_symbols, decision, closed_bars, evaluate_snapshots
from radar_quality import assess, quote_iex, evaluate_horizons, session_state
from breakout_engine import classify_breakout
from discovery_engine import fetch_candidates, fetch_asset_map, compare_scans
import streamlit as st
from alpaca.data.enums import DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderClass, OrderSide, QueryOrderStatus, TimeInForce
from alpaca.trading.requests import (GetOrdersRequest, GetPortfolioHistoryRequest,
                                     MarketOrderRequest, StopLossRequest, TakeProfitRequest)

# ======================= VARSAYILAN AYARLAR =======================
# Arka plan botu (worker) bu ayarları kullanır. GitHub'dan düzenleyebilirsin.
DEFAULTS = dict(
    watchlist="SOFI,F,PLUG,SNAP,RIOT,NIO,LCID,HOOD,PLTR,AMD",
    budget=30.0,        # işlem başına en fazla dolar
    max_pos=2,          # aynı anda en fazla pozisyon
    stop=2.0,           # zarar-durdur %
    take=4.0,           # kâr-al %
    daily_loss=5.0,     # günlük zarar limiti (dolar) - dolunca bot durur
    flatten_min=10,     # kapanıştan kaç dk önce hepsini sat
    strategies=["Gerçek Kırılım", "EMA20/50 Pullback"],
)
# ===================================================================


def secret(key, default=None):
    try:
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return os.environ.get(key, default)


PAPER = True  # Güvenlik: yalnızca sanal hesap


@st.cache_resource
def tc():
    return TradingClient(secret("ALPACA_KEY", secret("ALPACA_API_KEY")), secret("ALPACA_SECRET", secret("ALPACA_SECRET_KEY")), paper=PAPER)


@st.cache_resource
def dc():
    return StockHistoricalDataClient(secret("ALPACA_KEY", secret("ALPACA_API_KEY")), secret("ALPACA_SECRET", secret("ALPACA_SECRET_KEY")))


def notify(msg):
    """iPhone bildirimi (ntfy uygulaması). NTFY_TOPIC secret'ı gerekir."""
    topic = secret("NTFY_TOPIC")
    if not topic:
        return
    try:
        requests.post(f"https://ntfy.sh/{topic}", data=msg.encode("utf-8"),
                      headers={"Title": "Lab Nasdaq"}, timeout=8)
    except Exception:
        pass


# ======================= VERİ + GÖSTERGELER =======================
def indicators(df):
    d = df.index.date
    tp = (df.high + df.low + df.close) / 3
    df["ema9"] = df.close.ewm(span=9, adjust=False).mean()
    df["ema20"] = df.close.ewm(span=20, adjust=False).mean()
    df["ema50"] = df.close.ewm(span=50, adjust=False).mean()
    df["vwap"] = (tp * df.volume).groupby(d).cumsum() / df.volume.groupby(d).cumsum().replace(0, np.nan)
    rng = (df.high - df.low).replace(0, np.nan)
    df["delta"] = (df.volume * (2 * df.close - df.high - df.low) / rng).fillna(0)  # hacim deltası (tahmini)
    df["cdelta"] = df["delta"].groupby(d).cumsum()
    df["volma"] = df.volume.rolling(20, min_periods=5).mean().shift(1)
    return df


@st.cache_data(ttl=30, show_spinner=False)
def get_bars(sym, days=10):
    req = StockBarsRequest(symbol_or_symbols=sym, timeframe=TimeFrame(1, TimeFrameUnit.Minute),
                           start=datetime.now(timezone.utc) - timedelta(days=days), feed=DataFeed.IEX)
    try:
        df = dc().get_stock_bars(req).df
    except Exception as e:
        raise RuntimeError(f"Alpaca IEX veri hatası ({sym}): {type(e).__name__}: {e}") from e
    if df is None or df.empty:
        return None
    df = df.loc[sym].copy()
    df.index = df.index.tz_convert("America/New_York")
    df = df.between_time("09:30", "15:59")
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return indicators(df) if len(df) > 30 else None


# ======================= STRATEJİLER =======================
def s_ema_vwap(df):
    """Fiyat VWAP üstünde ve EMA9'u yukarı kesti."""
    return (df.close > df.vwap) & (df.close > df.ema9) & (df.close.shift(1) <= df.ema9.shift(1))


def break_level(df):
    return df.high.rolling(20).max().shift(1)


def s_break(df):
    """Historical closed-bar breakout: causal 20-bar resistance + first crossing + volume/body.
    Uses same thresholds as the live breakout engine. No pullback counted as breakout.
    """
    resistance = break_level(df)
    prev_resistance = resistance.shift(1)
    prev_close = df.close.shift(1)
    rng = (df.high - df.low).replace(0, np.nan)
    tr = pd.concat([(df.high - df.low), (df.high - df.close.shift(1)).abs(),
                    (df.low - df.close.shift(1)).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean().shift(1)
    buffer = (0.10 * atr / resistance).clip(lower=0.0005, upper=0.003)
    session = pd.Series(df.index.date, index=df.index)
    session_count = session.groupby(session).cumcount()
    contiguous = (df.index.to_series().diff().fillna(pd.Timedelta(minutes=1)) <= pd.Timedelta(minutes=2))
    # Full 20-bar window must be within current session.
    return ((session_count >= 21) & contiguous &
            (prev_close <= prev_resistance) & (df.close > resistance * (1 + buffer)) &
            ((df.close / resistance - 1) <= 0.012) &
            ((df.close - df.open) / rng >= 0.5) &
            (df.volume >= 1.5 * df.volma)).fillna(False)


def s_fvg(df):
    """Yükseliş FVG'si oluşur, fiyat boşluğun %50'sine geri gelip yukarı kapatırsa AL."""
    h, l, c, o = df.high.values, df.low.values, df.close.values, df.open.values
    d = df.index.date
    out = np.zeros(len(df), bool)
    zone = None
    for i in range(2, len(df)):
        strong = (c[i - 1] - o[i - 1]) > 0.5 * (h[i - 1] - l[i - 1] + 1e-9)
        if l[i] > h[i - 2] and c[i - 1] > o[i - 1] and strong and d[i] == d[i - 2]:
            zone = (h[i - 2], (h[i - 2] + l[i]) / 2, i)
            continue
        if zone:
            bot, mid, k = zone
            if i - k > 12 or c[i] < bot or d[i] != d[k]:
                zone = None
            elif l[i] <= mid and c[i] > bot and c[i] > o[i]:
                out[i] = True
                zone = None
    return pd.Series(out, index=df.index)


def whale_zones(df):
    big = (df.volume > 2 * df.volma) & (df.delta.abs() > 0.5 * df.volume)
    return big & (df.delta > 0), big & (df.delta < 0)


def s_whale(df):
    """Balina alış bölgesi (hacim deltası): fiyat bölgeye geri dönüp yukarı kapatırsa AL."""
    buy, _ = whale_zones(df)
    b = buy.values
    h, l, c, o = df.high.values, df.low.values, df.close.values, df.open.values
    out = np.zeros(len(df), bool)
    zl = zh = None
    k = 0
    for i in range(len(df)):
        if b[i]:
            zl, zh, k = l[i], h[i], i
            continue
        if zl is not None:
            if i - k > 30 or c[i] < zl:
                zl = None
            elif l[i] <= zh and c[i] > o[i] and c[i] > zl:
                out[i] = True
                zl = None
    return pd.Series(out, index=df.index)


def s_trend_pullback(df):
    """1m EMA20>EMA50, prior 1-5 bars touched EMA band, current bullish engulfing."""
    up = (df.ema20 > df.ema50) & (df.ema20.diff() > 0)
    band_low = pd.concat([df.ema20, df.ema50], axis=1).min(axis=1)
    band_high = pd.concat([df.ema20, df.ema50], axis=1).max(axis=1)
    touched = (df.low <= band_high) & (df.high >= band_low)
    # Only earlier bars qualify; never use current bar as both pullback and entry.
    recent = touched.shift(1).rolling(5, min_periods=1).max().fillna(0).astype(bool)
    prev_bear = df.close.shift(1) < df.open.shift(1)
    bullish = (df.close > df.open) & prev_bear & (df.open <= df.close.shift(1)) & (df.close >= df.open.shift(1))
    same_day = df.index.date == pd.Series(df.index.date, index=df.index).shift(1).values
    return (up & recent & bullish & same_day & (df.close > df.ema20)).fillna(False)


def pullback_levels(df, method="Swing"):
    """Informational long-only entry/stop/2R based on closed bars."""
    if len(df) < 55: return None
    entry = float(df.close.iloc[-1])
    prior = df.iloc[-10:]
    tr = pd.concat([df.high-df.low, (df.high-df.close.shift(1)).abs(),
                    (df.low-df.close.shift(1)).abs()], axis=1).max(axis=1)
    atr = float(tr.rolling(14, min_periods=14).mean().iloc[-1])
    stop = float(prior.low.min()) if method == "Swing" else entry - 1.5*atr
    if not (0 < stop < entry):return None
    return {"Giriş": round(entry,3), "Stop": round(stop,3), "Hedef (2R)": round(entry+2*(entry-stop),3),
            "Risk %": round(100*(entry-stop)/entry,2)}


STRATS = {"EMA9+VWAP": s_ema_vwap, "Gerçek Kırılım": s_break, "FVG %50": s_fvg, "Balina Bölgesi": s_whale, "EMA20/50 Pullback": s_trend_pullback}


# ======================= BACKTEST =======================
def backtest(df, sig, stop, take, hold=24, cost=0.002):
    """Kapanmış sinyal mumundan SONRAKİ mum açılışı; çift dokunuşta stop önce.
    cost: toplam gidiş-dönüş komisyon + kayma varsayımı (varsayılan %0,20).
    Sonuçlar IEX mumlarından yapılan yaklaşık simülasyondur, gerçekleşmiş işlem değildir.
    """
    o, h, l, c = [df[x].to_numpy(dtype=float) for x in ("open", "high", "low", "close")]
    idx, dates = df.index, df.index.date
    sv = sig.reindex(idx).fillna(False).to_numpy(dtype=bool)
    trades = []
    i = 0
    while i < len(df)-1:
        if not sv[i] or dates[i+1] != dates[i]:
            i += 1
            continue
        j = i + 1
        entry = o[j]
        if not np.isfinite(entry) or entry <= 0:
            i += 1
            continue
        sl, tp = entry * (1-stop/100), entry * (1+take/100)
        k = j
        while True:
            # Açılış gap'i stopun altındaysa stop fiyatından gerçekleştiğini varsayma.
            if o[k] <= sl:
                ex, reason = o[k], "stop gap"
                break
            if l[k] <= sl:
                ex, reason = sl, "stop"
                break
            if h[k] >= tp:
                ex, reason = tp, "hedef"
                break
            if k == len(df)-1 or k-j >= hold or dates[k+1] != dates[k]:
                ex, reason = c[k], "süre/seans"
                break
            k += 1
        trades.append((idx[j], float(entry), float(ex), float(ex/entry-1-cost), reason))
        i = k+1
    return pd.DataFrame(trades, columns=["zaman", "giriş", "çıkış", "getiri", "çıkış nedeni"])


def stats(t):
    if t.empty:
        return {"İşlem": 0, "Kazanma %": 0.0, "Kâr faktörü": 0.0, "Toplam %": 0.0, "Maks düşüş %": 0.0, "Ödül/risk": 0.0}
    r = t["getiri"]
    w, ls = r[r > 0], r[r <= 0]
    eq = (1 + r).cumprod()
    dd = (eq / eq.cummax() - 1).min()
    pf = w.sum() / abs(ls.sum()) if ls.sum() != 0 else (99 if w.sum() > 0 else 0)
    rr = w.mean() / abs(ls.mean()) if len(w) and len(ls) and ls.mean() != 0 else 0
    return {"İşlem": len(r), "Kazanma %": round(100 * len(w) / len(r), 1), "Kâr faktörü": round(min(pf, 99), 2),
            "Toplam %": round(100 * (eq.iloc[-1] - 1), 1), "Maks düşüş %": round(100 * dd, 1), "Ödül/risk": round(rr, 2)}


# ======================= SIRALAMA / RADAR =======================
def analyze(sym, strategies, stop, take):
    df = get_bars(sym, 10)
    if df is None or len(df) < 60:
        return None
    # Henüz kapanmamış veya eski mumdan canlı işlem sinyali üretme.
    now_ny = pd.Timestamp.now(tz="America/New_York")
    if df.index[-1] + pd.Timedelta(minutes=1) > now_ny:
        df = df.iloc[:-1]
    if len(df) < 60:
        return None
    age = (now_ny - (df.index[-1] + pd.Timedelta(minutes=1))).total_seconds() / 60
    if age > 2 or age < 0:
        return None
    if (df.index[-1] - df.index[-2]).total_seconds() > 120:
        return None
    last = df.iloc[-1]
    price = float(last.close)
    active, pfs = [], []
    for name in strategies:
        sig = STRATS[name](df)
        if bool(sig.iloc[-1]):
            active.append(name)
        s = stats(backtest(df, sig, stop, take))
        if s["İşlem"] >= 3:
            pfs.append(s["Kâr faktörü"])
    rvol = float(np.nan_to_num(last.volume / df.volma.iloc[-1])) if df.volma.iloc[-1] else 0.0
    trend = price > last.vwap and price > last.ema9
    why = []
    if active:
        why.append("Sinyal: " + ", ".join(active))
    if trend:
        why.append("VWAP ve EMA9 üstünde")
    if last.cdelta > 0:
        why.append("Hacim deltası pozitif")
    if rvol >= 1.5:
        why.append(f"Hacim {rvol:.1f}x")
    score = len(active) * 30 + min(rvol, 3) * 10 + (15 if trend else 0) + (10 if last.cdelta > 0 else 0) \
        + (min(float(np.mean(pfs)), 3) * 5 if pfs else 0)
    # One causal breakout engine for all screens. Pullback is NOT a breakout.
    breakout = classify_breakout(df, now_ny)
    confirmed = breakout['Kırılım durumu'] == 'TEYİTLİ KIRILIM'
    state = "TEYİTLİ KIRILIM / SANAL" if confirmed and trend else "İZLE — KIRILIM YOK"
    return {"Durum": state, "Veri yaşı dk": round(age, 1), "Hisse": sym, "Skor": min(100, round(score)), "Fiyat": round(price, 2), "Sinyal": ", ".join(active) or "-",
            "Hacim x": round(rvol, 1), "Kırılım": breakout.get("Direnç"), "Kırılım durumu": breakout["Kırılım durumu"],
            "Dirence uzaklık %": breakout.get("Dirence uzaklık %"), "Kırılım gerekçesi": breakout["Kırılım gerekçesi"],
            "Alış": round(price, 2), "Stop": round(price * (1 - stop / 100), 2),
            "Hedef": round(price * (1 + take / 100), 2), "Neden": "; ".join(why) or "Belirgin sinyal yok"}


@st.cache_data(ttl=30, show_spinner=False)
def scan(wl, strategies, stop, take):
    rows = []
    for s in wl:
        try:
            r = analyze(s, list(strategies), stop, take)
        except Exception as e:
            r = None
        if r:
            rows.append(r)
    return pd.DataFrame(rows).sort_values("Skor", ascending=False).reset_index(drop=True) if rows else pd.DataFrame()


def radar(wl):
    """Ani hareket radarı (1 dk mum): henüz fırlamamış ama yükselme belirtisi gösterenler."""
    rows = []
    for s in wl:
        df = get_bars(s, 5)
        if df is None or len(df) < 30:
            continue
        now_ny = pd.Timestamp.now(tz="America/New_York")
        if df.index[-1] + pd.Timedelta(minutes=1) > now_ny:
            df = df.iloc[:-1]
        if len(df) < 30: continue
        age = (now_ny - (df.index[-1] + pd.Timedelta(minutes=1))).total_seconds()/60
        last = df.iloc[-1]
        day = df[df.index.date == df.index[-1].date()]
        # Tam 15 dakika önceki kapanış, aynı seans ve yeterli bar varsa.
        today = day.tail(16)
        move15 = (last.close / today.close.iloc[0] - 1) * 100 if len(today) == 16 and (today.index[-1]-today.index[0]).total_seconds() == 900 else float("nan")
        from_open = (last.close / day.open.iloc[0] - 1) * 100
        rvol = float(np.nan_to_num(last.volume / df.volma.iloc[-1])) if df.volma.iloc[-1] else 0.0
        ok = (np.isfinite(move15) and last.close > last.vwap and last.close > last.ema9 and last.cdelta > 0
              and rvol >= 1.8 and 0.3 <= move15 <= 3 and from_open < 6)
        status = ("⚪ Piyasa kapalı / eski veri" if age > 2 else
                  ("🟢 İzle — ön aday" if ok else ("🔴 Zaten yükselmiş" if from_open >= 6 else "⚪ İzle")))
        rows.append({"Hisse": s, "Durum": status, "Fiyat": round(float(last.close), 2),
                     "15dk %": round(float(move15), 2), "Günlük %": round(float(from_open), 2), "Hacim x": round(rvol, 1)})
    return pd.DataFrame(rows).sort_values("Durum").reset_index(drop=True) if rows else pd.DataFrame()


# ======================= BOT =======================
def parse_wl(s):
    return [x.strip().upper() for x in str(s).split(",") if x.strip()]


def run_cycle(cfg):
    """Emir gönderme hiçbir koşulda etkin değil; analiz amaçlı."""
    return ["GÜVENLİ MOD: Otomatik alım/satım devre dışı. Yalnızca sanal test."]


def worker():
    cfg = dict(DEFAULTS)
    cfg["watchlist"] = os.environ.get("WATCHLIST", cfg["watchlist"])
    print("Mod:", "PAPER" if PAPER else "CANLI")
    for line in run_cycle(cfg):
        print(line)


# ======================= ARAYÜZ =======================
def chart(df, sig=None, lines=None):
    d = df.tail(234)
    x = d.index.tz_localize(None)
    fig = go.Figure(go.Candlestick(x=x, open=d.open, high=d.high, low=d.low, close=d.close, name="Fiyat"))
    fig.add_scatter(x=x, y=d.ema9, name="EMA9", line=dict(width=1.5, color="#f59e0b"))
    fig.add_scatter(x=x, y=d.vwap, name="VWAP", line=dict(width=1.5, color="#a78bfa"))
    if sig is not None:
        m = sig.reindex(d.index).fillna(False).values
        fig.add_scatter(x=x[m], y=d.low.values[m] * 0.998, mode="markers", name="AL",
                        marker=dict(symbol="triangle-up", size=11, color="#22c55e"))
    for name, y, color in (lines or []):
        fig.add_hline(y=y, line_dash="dot", line_color=color, annotation_text=name)
    fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"]), dict(bounds=[16, 9.5], pattern="hour")])
    fig.update_layout(height=420, margin=dict(l=0, r=0, t=10, b=0), xaxis_rangeslider_visible=False,
                      paper_bgcolor="#0a1a3a", plot_bgcolor="#0a1a3a", font_color="#e6edff",
                      legend=dict(orientation="h"))
    return fig


def ui():
    st.set_page_config(page_title="Lab Nasdaq", page_icon="📈", layout="wide")
    pin = secret("APP_PIN")
    if pin and not st.session_state.get("ok"):
        x = st.text_input("PIN", type="password")
        if x and x == str(pin):
            st.session_state.ok = True
            st.rerun()
        st.stop()
    if not secret("ALPACA_KEY", secret("ALPACA_API_KEY")) or not secret("ALPACA_SECRET", secret("ALPACA_SECRET_KEY")):
        st.error("ALPACA_KEY ve ALPACA_SECRET Streamlit Secrets'a eklenmeli.")
        st.stop()

    st.title("📈 Lab Nasdaq v6.8 — Doğrulama Radarı")
    st.warning("IEX tek borsa verisidir; tüm NASDAQ hacmi değildir. Buradaki sinyaller gerçek alım önerisi değil, test adaylarıdır.")
    st.caption(("🧪 SANAL (paper) hesap" if PAPER else "⚠️ CANLI hesap") + " • Yatırım tavsiyesi değildir")

    with st.expander("⚙️ Ayarlar"):
        wl_txt = st.text_input("Hisse listesi", DEFAULTS["watchlist"])
        c1, c2 = st.columns(2)
        budget = c1.number_input("İşlem başı $", 5.0, 10000.0, DEFAULTS["budget"])
        max_pos = c2.number_input("Maks pozisyon", 1, 10, DEFAULTS["max_pos"])
        stop = c1.number_input("Stop %", 0.5, 20.0, DEFAULTS["stop"])
        take = c2.number_input("Hedef %", 0.5, 50.0, DEFAULTS["take"])
        dl = c1.number_input("Günlük zarar limiti $", 1.0, 10000.0, DEFAULTS["daily_loss"])
        strat = st.multiselect("Bot stratejileri", list(STRATS), DEFAULTS["strategies"])
    cfg = dict(watchlist=wl_txt, budget=budget, max_pos=int(max_pos), stop=stop, take=take,
               daily_loss=dl, flatten_min=DEFAULTS["flatten_min"], strategies=strat or list(STRATS))
    wl = parse_wl(wl_txt)
    st.subheader("🔎 Dinamik hisse keşfi (deneysel)")
    st.caption("Seans: " + session_state() + " • Sadece normal seans sinyalleri işlem adayı olarak değerlendirilir.")
    st.caption("Alpaca en çok işlem görenler ve yükselenler listesi; veri gecikmesi/kapsamı garanti edilmez. En fazla 20 yeni sembol eklenir. Sadece sanal izleme.")
    st.caption("Liste aynı kalabilir: bu kaynaklar günün en hareketli hisselerini gösterir; tüm piyasayı taramaz.")
    @st.cache_data(ttl=3600, show_spinner=False)
    def validated_assets(api_key, api_secret):
        return fetch_asset_map(api_key, api_secret)
    if st.button("Yeni adayları keşfet"):
        key = secret("ALPACA_KEY", secret("ALPACA_API_KEY"))
        sec = secret("ALPACA_SECRET", secret("ALPACA_SECRET_KEY"))
        with st.spinner("Alpaca listeleri ve hisse türleri doğrulanıyor..."):
            try:
                assets = validated_assets(key, sec) if key and sec else None
                scan = fetch_candidates(key, sec, asset_map=assets)
            except Exception as exc:
                scan = {'symbols': [], 'details': [], 'rejected': [], 'errors': [f'Doğrulama hatası: {type(exc).__name__}: {str(exc)[:140]}'], 'checked_at_utc': datetime.now(timezone.utc).isoformat()}
        prior = st.session_state.get('discovery_scan', {}).get('symbols', [])
        changes = compare_scans(prior, scan['symbols'])
        scan['changes'] = changes
        st.session_state['discovery_scan'] = scan
        history = st.session_state.setdefault('discovery_history', [])
        history.append({'UTC': scan['checked_at_utc'], 'Bulunan': len(scan['symbols']), 'Yeni': len(changes['new']), 'Çıkan': len(changes['removed']), 'Aynı': len(changes['unchanged'])})
        st.session_state['discovery_history'] = history[-100:]
    scan = st.session_state.get('discovery_scan', {})
    discovered = scan.get('symbols', [])
    if scan:
        st.caption(f"Son API denemesi (UTC): {scan.get('checked_at_utc', '?')} • Kaynak: Alpaca movers / most-actives")
        change = scan.get('changes', {})
        st.write(f"Yeni: {len(change.get('new', []))} • Çıkan: {len(change.get('removed', []))} • Aynı kalan: {len(change.get('unchanged', []))}")
        if change.get('new'): st.success('Yeni eklenenler: ' + ', '.join(change['new']))
        if change.get('removed'): st.info('Listeden çıkanlar: ' + ', '.join(change['removed']))
        if discovered:
            st.write('Doğrulanmış normal hisseler: ' + ', '.join(discovered))
            st.dataframe(pd.DataFrame(scan.get('details', [])), hide_index=True)
        if scan.get('rejected'):
            st.caption(f"Normal hisse olarak doğrulanamayan {len(scan['rejected'])} sembol elendi.")
            with st.expander('Elenen semboller ve nedenleri'):
                st.dataframe(pd.DataFrame(scan['rejected']), hide_index=True)
        for err in scan.get('errors', []): st.warning('Keşif sorunu: ' + err)
        if st.session_state.get('discovery_history'):
            st.dataframe(pd.DataFrame(st.session_state['discovery_history']), hide_index=True)
            st.download_button('Keşif geçmişini CSV indir', pd.DataFrame(st.session_state['discovery_history']).to_csv(index=False).encode('utf-8-sig'), 'kesif_gecmisi.csv', 'text/csv')
    use_discovered = st.checkbox('Keşfedilen hisseleri mevcut listeye ekle', value=True)
    if use_discovered:
        wl = list(dict.fromkeys(wl + discovered))[:35]
    st.caption(f'Bu oturumda taranacak hisse sayısı: {len(wl)}. API istekleri taramayı yavaşlatabilir.')

    t_radar, t_rank, t_lab, t_perf, t_bot, t_quality = st.tabs(["📡 Radar", "🏆 Sıralama", "🧪 Lab", "📊 Performans", "🤖 Bot", "🛡️ Kalite & Kayıt"])

    with t_radar:
        st.caption("1 dk mum: hacim artışı + VWAP/EMA9 üstü + pozitif hacim deltası, henüz fırlamamış hisseler")
        if st.button("Yenile", key="r1"):
            st.cache_data.clear()
        with st.spinner("Taranıyor..."):
            rd = radar(wl)
        if not rd.empty:
            st.dataframe(rd, hide_index=True)
        else:
            st.info("Veri yok (piyasa kapalı olabilir).")

    with t_rank:
        st.caption("Tek kırılım motoru: 20 önceki mumun direnci, gerçek geçiş, hacim ve mum gövdesi. Bid/ask olmadan AL tavsiyesi üretmez.")
        if st.button("Adayları ayrıntılı değerlendir"):
            checks=[]
            for symbol in wl:
                try:
                    bars=get_bars(symbol, 3)
                    checks.append({"Hisse":symbol, **classify_breakout(bars)})
                except Exception as exc:
                    checks.append({"Hisse":symbol,"Karar":"VERİ HATASI","Neden":str(exc)[:180]})
            st.session_state['radar_checks']=checks
        if st.session_state.get('radar_checks'):
            st.dataframe(pd.DataFrame(st.session_state['radar_checks']),hide_index=True)
            st.download_button("Değerlendirmeleri CSV indir", pd.DataFrame(st.session_state['radar_checks']).to_csv(index=False).encode('utf-8-sig'),"radar_degerlendirme.csv","text/csv")
        with st.spinner("Hisseler analiz ediliyor..."):
            sc = scan(tuple(wl), tuple(cfg["strategies"]), stop, take)
        if sc.empty:
            st.info("Canlı aday yok: piyasa kapalı, veri eski veya son mumda koşullar sağlanmadı. Radar sekmesinde son kapanış verilerini görebilirsin.")
        else:
            for _, r in sc.head(3).iterrows():
                if r.get("Durum") == "TEYİTLİ KIRILIM / SANAL":
                    st.success(f"**{r['Hisse']}** (sanal test) skor {r['Skor']} • Alış {r['Alış']} • Stop {r['Stop']} • "
                               f"Hedef {r['Hedef']} • Kırılım {r['Kırılım']}\n\n{r['Neden']}")
            st.dataframe(sc, hide_index=True)

    with t_lab:
        st.caption("Sinyal günlüğü yalnızca bu Streamlit oturumunda saklanır; uygulama yeniden başlarsa silinebilir. CSV olarak indir.")
        if 'signal_log' not in st.session_state:
            st.session_state['signal_log']=[]
        if st.button("Şimdiki gözlemleri günlüğe ekle"):
            stamp=pd.Timestamp.now(tz='America/New_York')
            for symbol in wl:
                try:
                    bars=get_bars(symbol, 3)
                    result=classify_breakout(bars, stamp)
                    if result.get('Kırılım durumu') in ('TEYİTLİ KIRILIM','DİRENCE YAKIN'):
                        st.session_state['signal_log'].append({'Zaman':stamp,'Hisse':symbol,'Fiyat':result['Fiyat'],'Karar':result['Kırılım durumu'],'Durum':'BEKLİYOR','5dk %':None})
                except Exception:
                    pass
            st.success('Gözlemler oturum günlüğüne eklendi (varsa).')
        if st.button("Günlüğü son fiyatlarla değerlendir"):
            latest={}
            for symbol in set(x['Hisse'] for x in st.session_state['signal_log'] if x['Durum']=='BEKLİYOR'):
                try:
                    bars=closed_bars(get_bars(symbol, 3))
                    if bars is not None and not bars.empty:
                        latest[symbol]=(bars.index[-1],float(bars.close.iloc[-1]))
                except Exception:
                    pass
            st.session_state['signal_log']=evaluate_snapshots(st.session_state['signal_log'],latest)
        if st.session_state['signal_log']:
            logdf=pd.DataFrame(st.session_state['signal_log'])
            st.dataframe(logdf,hide_index=True)
            st.download_button("Sinyal günlüğünü CSV indir",logdf.to_csv(index=False).encode('utf-8-sig'),"sinyal_gunlugu.csv","text/csv")
        sym = st.selectbox("Hisse", wl)
        df = get_bars(sym, 10)
        if df is None:
            st.info("Veri yok.")
        else:
            # En son tamamlanmamış mumu dışla, testte ileriye bakma.
            now_ny = pd.Timestamp.now(tz="America/New_York")
            if df.index[-1] + pd.Timedelta(minutes=1) > now_ny:
                df = df.iloc[:-1]
            rows = [{"Strateji": n, **stats(backtest(df, f(df), stop, take))} for n, f in STRATS.items()]
            st.dataframe(pd.DataFrame(rows), hide_index=True)
            st.caption("Kâr faktörü 1 altındaysa strateji testte zarar etti. 30 işlem altındaki örnekler karar için yetersizdir. Test maliyeti toplam %0,20 varsayılmıştır; gerçek spread/kayma ölçülmemiştir.")
            pick = st.selectbox("Grafikte göster", list(STRATS))
            sig = STRATS[pick](df)
            lv = float(break_level(df).iloc[-1])
            p = float(df.close.iloc[-1])
            st.plotly_chart(chart(df, sig, [("Kırılım", lv, "#38bdf8"), ("Stop", p * (1 - stop / 100), "#ef4444"),
                                            ("Hedef", p * (1 + take / 100), "#22c55e")]))
            st.caption("Backtest son 10 gün, 1 dk IEX mum; varsayımsal toplam işlem maliyeti %0,20. Geçmiş sonuç geleceği garanti etmez.")
            if pick == "EMA20/50 Pullback":
                method = st.radio("Stop yöntemi", ["Swing", "ATR"], horizontal=True)
                lvls = pullback_levels(df, method)
                st.write("Son mum için örnek risk planı (yalnızca eğitim):", lvls if lvls else "Geçerli plan yok")
                st.caption("Sinyal ancak son kapanmış mumda engulfing ve EMA koşulları varsa oluşur; bu tablo canlı alış emri değildir.")

    with t_perf:
        try:
            t = tc()
            a = t.get_account()
            eq, last_eq = float(a.equity), float(a.last_equity)
            m1, m2, m3 = st.columns(3)
            m1.metric("Portföy $", f"{eq:,.2f}", f"{eq - last_eq:+.2f} bugün")
            m2.metric("Nakit $", f"{float(a.cash):,.2f}")
            m3.metric("Alım gücü $", f"{float(a.buying_power):,.2f}")
            try:
                ph = t.get_portfolio_history(GetPortfolioHistoryRequest(period="1M", timeframe="1D"))
                s = pd.Series(ph.equity, index=pd.to_datetime(ph.timestamp, unit="s")).dropna()
                s = s[s > 0]
                if len(s) > 1:
                    fig = go.Figure(go.Scatter(x=s.index, y=s.values, line=dict(color="#3b82f6")))
                    fig.update_layout(height=260, margin=dict(l=0, r=0, t=10, b=0), paper_bgcolor="#0a1a3a",
                                      plot_bgcolor="#0a1a3a", font_color="#e6edff")
                    st.plotly_chart(fig)
                    mdd = (s / s.cummax() - 1).min() * 100
                    st.write(f"1 ay getiri: **{(s.iloc[-1] / s.iloc[0] - 1) * 100:+.2f}%** • "
                             f"Maks düşüş: **{mdd:.2f}%**")
            except Exception:
                pass
            pos = t.get_all_positions()
            st.subheader("Açık pozisyonlar")
            if pos:
                st.dataframe(pd.DataFrame([{"Hisse": p.symbol, "Adet": p.qty, "Giriş": float(p.avg_entry_price),
                                            "Şimdi": float(p.current_price), "K/Z $": float(p.unrealized_pl),
                                            "K/Z %": round(float(p.unrealized_plpc) * 100, 2)} for p in pos]),
                             hide_index=True)
            else:
                st.caption("Açık pozisyon yok.")
            st.subheader("Son işlemler")
            done = [o for o in t.get_orders(GetOrdersRequest(status=QueryOrderStatus.CLOSED, limit=50))
                    if o.filled_qty and float(o.filled_qty) > 0]
            if done:
                st.dataframe(pd.DataFrame([{"Zaman": o.filled_at, "Hisse": o.symbol, "Yön": o.side.value,
                                            "Adet": o.filled_qty, "Fiyat": o.filled_avg_price} for o in done]),
                             hide_index=True)
        except Exception as e:
            st.error(f"Hesap okunamadı: {e}")

    with t_quality:
        st.subheader("🛡️ Sinyal doğrulama — gerçek emir verilmez")
        st.caption("IEX mumları ve IEX bid/ask fiyatları; tüm NASDAQ verisi değildir. Bid/ask bulunmazsa AL kararı verilmez.")
        if 'quality_log' not in st.session_state:
            st.session_state['quality_log']=[]
        if st.button("Güncel adayları doğrula", key='quality_check'):
            key=secret("ALPACA_KEY",secret("ALPACA_API_KEY"))
            sec=secret("ALPACA_SECRET",secret("ALPACA_SECRET_KEY"))
            quotes,err=quote_iex(key,sec,wl)
            if err: st.warning("Kotasyon hatası: "+err)
            now=pd.Timestamp.now(tz='America/New_York')
            rows=[]
            for symbol in wl:
                try:
                    bars=get_bars(symbol,3)
                    q=quotes.get(symbol)
                    # Quote must be fresh and not future-dated.
                    if q and q.get('timestamp'):
                        qt=pd.Timestamp(q['timestamp']).tz_convert('America/New_York')
                        if abs((now-qt).total_seconds())>120: q=None
                    result=assess(bars,now,q)
                    rows.append({'Hisse':symbol,**result})
                    if result['Karar'] in ('KIRILIM ADAYI / SANAL','DİRENÇ YAKIN / SANAL') and bars is not None:
                        completed=closed_bars(bars,now)
                        stamp=completed.index[-1]
                        unique=(symbol,str(stamp),result['Karar'])
                        if not any((r['Hisse'],r['Sinyal mumu'],r['Karar'])==unique for r in st.session_state['quality_log']):
                            st.session_state['quality_log'].append({'Hisse':symbol,'Sinyal mumu':str(stamp),'Karar':result['Kırılım durumu'],'Fiyat':result['Fiyat'],'Spread %':result.get('Spread %'),'Hacim x':result.get('Hacim x')})
                except Exception as exc:
                    rows.append({'Hisse':symbol,'Karar':'VERİ HATASI','Neden':str(exc)[:200]})
            st.session_state['quality_rows']=rows
        if st.session_state.get('quality_rows'):
            st.dataframe(pd.DataFrame(st.session_state['quality_rows']),hide_index=True)
            st.download_button('Değerlendirme CSV indir',pd.DataFrame(st.session_state['quality_rows']).to_csv(index=False).encode('utf-8-sig'),'kalite_kontrol.csv','text/csv')
        st.subheader('İleriye dönük sinyal günlüğü')
        st.caption('Kayıtlar yalnızca bu oturumda tutulur. 1/5/10/30 dakika için tam hedef mum yoksa sonuç boş kalır; son fiyatla doldurulmaz. İşlem gerçekleşmesi veya net getiri değildir.')
        if st.button('Sinyal sonuçlarını ölç',key='quality_evaluate'):
            bars_by_symbol={}
            for sym in set(r['Hisse'] for r in st.session_state['quality_log']):
                try:
                    bars_by_symbol[sym]=closed_bars(get_bars(sym,3))
                except Exception as exc:
                    st.warning(f'{sym}: {type(exc).__name__}')
            st.session_state['quality_log']=evaluate_horizons(st.session_state['quality_log'],bars_by_symbol)
        if st.session_state['quality_log']:
            log=pd.DataFrame(st.session_state['quality_log'])
            st.dataframe(log,hide_index=True)
            st.download_button('Sinyal günlüğünü CSV indir',log.to_csv(index=False).encode('utf-8-sig'),'ileri_test_sinyalleri.csv','text/csv')
        else:
            st.info('Henüz kayıt yok. Normal seans sırasında Güncel adayları doğrula düğmesini kullan.')

    with t_bot:
        st.subheader("🛡️ Güvenli test modu")
        st.info("Otomatik emir verme kapalı. Önce yeterli sayıda tarihsel ve ileriye dönük testte maliyet sonrası pozitif sonuç gerekli.")
        if st.button("Sanal sinyal taramasını çalıştır"):
            sc = scan(tuple(wl), tuple(cfg["strategies"]), stop, take)
            if sc.empty:
                st.warning("Güncel teyitli sinyal yok veya piyasa kapalı.")
            else:
                st.dataframe(sc, hide_index=True)
        st.caption("Gerçek alım/satım için Midas'a otomatik bağlantı yoktur. Alpaca hesabına emir gönderilmez.")



if "--worker" in sys.argv:
    worker()
else:
    ui.__globals__["scan"] = globals()["scan"]
    ui()

