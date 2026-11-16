"""
Lab Nasdaq Bot - tek dosya (app.py)
- iPhone'da Streamlit uygulaması olarak çalışır
- Aynı dosya GitHub Actions'ta arka plan botu olarak da çalışır:  python app.py --worker
Varsayılan: PAPER (sanal para). Canlı için ALPACA_PAPER=false secret'ı gerekir.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
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
    strategies=["EMA9+VWAP", "Gerçek Kırılım", "FVG %50", "Balina Bölgesi"],
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
    df["vwap"] = (tp * df.volume).groupby(d).cumsum() / df.volume.groupby(d).cumsum()
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
    except Exception:
        return None
    if df is None or df.empty:
        return None
    df = df.loc[sym].copy()
    df.index = df.index.tz_convert("America/New_York")
    df = df.between_time("09:30", "15:59")
    return indicators(df) if len(df) > 30 else None


# ======================= STRATEJİLER =======================
def s_ema_vwap(df):
    """Fiyat VWAP üstünde ve EMA9'u yukarı kesti."""
    return (df.close > df.vwap) & (df.close > df.ema9) & (df.close.shift(1) <= df.ema9.shift(1))


def break_level(df):
    return df.high.rolling(20).max().shift(1)


def s_break(df):
    """Gerçek kırılım: gövde kapanışla direnç üstünde (fitil değil), güçlü gövde (displacement), hacim onayı."""
    rng = (df.high - df.low).replace(0, np.nan)
    return ((df.close > break_level(df) * 1.001) & ((df.close - df.open) / rng > 0.5)
            & (df.volume > 1.3 * df.volma))


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


STRATS = {"EMA9+VWAP": s_ema_vwap, "Gerçek Kırılım": s_break, "FVG %50": s_fvg, "Balina Bölgesi": s_whale}


# ======================= BACKTEST =======================
def backtest(df, sig, stop, take, hold=24, cost=0.001):
    o, h, l, c = df.open.values, df.high.values, df.low.values, df.close.values
    idx, dates = df.index, df.index.date
    sv = sig.fillna(False).values
    n = len(df)
    trades = []
    i = 0
    while i < n - 1:
        if not sv[i]:
            i += 1
            continue
        j = i + 1
        if dates[j] != dates[i]:
            i += 1
            continue
        entry = o[j]
        sl, tp = entry * (1 - stop / 100), entry * (1 + take / 100)
        k = j
        while True:
            if l[k] <= sl:
                ex = sl
                break
            if h[k] >= tp:
                ex = tp
                break
            if k == n - 1 or k - j >= hold or dates[k + 1] != dates[k]:
                ex = c[k]
                break
            k += 1
        trades.append((idx[j], entry, ex, ex / entry - 1 - cost))
        i = k + 1
    return pd.DataFrame(trades, columns=["zaman", "giriş", "çıkış", "getiri"])


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
    # Kırılım doğrulanmadıysa alış tavsiyesi verme.
    confirmed = bool(s_break(df).iloc[-1])
    state = "KIRILIM TEYİDİ / SANAL TEST" if confirmed else "İZLE — KIRILIM YOK"
    return {"Durum": state, "Veri yaşı dk": round(age, 1), "Hisse": sym, "Skor": min(100, round(score)), "Fiyat": round(price, 2), "Sinyal": ", ".join(active) or "-",
            "Hacim x": round(rvol, 1), "Kırılım": round(float(break_level(df).iloc[-1]), 2),
            "Alış": round(price, 2), "Stop": round(price * (1 - stop / 100), 2),
            "Hedef": round(price * (1 + take / 100), 2), "Neden": "; ".join(why) or "Belirgin sinyal yok"}


@st.cache_data(ttl=30, show_spinner=False)
def scan(wl, strategies, stop, take):
    rows = []
    for s in wl:
        try:
            r = analyze(s, list(strategies), stop, take)
        except Exception:
            r = None
        if r:
            rows.append(r)
    return pd.DataFrame(rows).sort_values("Skor", ascending=False).reset_index(drop=True) if rows else pd.DataFrame()


def radar(wl):
    """Ani hareket radarı (5 dk mum): henüz fırlamamış ama yükselme belirtisi gösterenler."""
    rows = []
    for s in wl:
        df = get_bars(s, 5)
        if df is None or len(df) < 30:
            continue
        last = df.iloc[-1]
        day = df[df.index.date == df.index[-1].date()]
        move15 = (last.close / df.close.iloc[-4] - 1) * 100
        from_open = (last.close / day.open.iloc[0] - 1) * 100
        rvol = float(np.nan_to_num(last.volume / df.volma.iloc[-1])) if df.volma.iloc[-1] else 0.0
        ok = (last.close > last.vwap and last.close > last.ema9 and last.cdelta > 0
              and rvol >= 1.8 and 0.3 <= move15 <= 3 and from_open < 6)
        status = "🟢 Yükselme adayı" if ok else ("🔴 Zaten yükselmiş" if from_open >= 6 else "⚪ İzle")
        rows.append({"Hisse": s, "Durum": status, "Fiyat": round(float(last.close), 2),
                     "15dk %": round(float(move15), 2), "Günlük %": round(float(from_open), 2), "Hacim x": round(rvol, 1)})
    return pd.DataFrame(rows).sort_values("Durum").reset_index(drop=True) if rows else pd.DataFrame()


# ======================= BOT =======================
def parse_wl(s):
    return [x.strip().upper() for x in str(s).split(",") if x.strip()]


def run_cycle(cfg):
    if not bool(secret("ENABLE_PAPER_ORDERS", False)):
        return ["GÜVENLİ MOD: Otomatik emirler kapalı. ENABLE_PAPER_ORDERS=true yalnızca sanal emirleri açar."]
    log = []
    t = tc()
    clock = t.get_clock()
    if not clock.is_open:
        return ["Piyasa kapalı."]
    acct = t.get_account()
    pos = t.get_all_positions()
    if float(acct.last_equity) - float(acct.equity) >= cfg["daily_loss"]:
        if pos:
            t.close_all_positions(cancel_orders=True)
            notify("Günlük zarar limiti doldu. Tüm pozisyonlar kapatıldı, bot durdu.")
        return ["Günlük zarar limiti doldu. Yeni işlem yok."]
    if clock.next_close - clock.timestamp < timedelta(minutes=cfg["flatten_min"]):
        if pos:
            t.close_all_positions(cancel_orders=True)
            notify("Kapanışa yakın: pozisyonlar kapatıldı.")
        return ["Kapanışa yakın: pozisyonlar kapatıldı, yeni işlem yok."]
    held = {p.symbol for p in pos}
    pending = {o.symbol for o in t.get_orders(GetOrdersRequest(status=QueryOrderStatus.OPEN))}
    df = scan(tuple(parse_wl(cfg["watchlist"])), tuple(cfg["strategies"]), cfg["stop"], cfg["take"])
    if df.empty:
        return ["Veri alınamadı."]
    for _, r in df.iterrows():
        if r.get("Durum") != "KIRILIM TEYİDİ / SANAL TEST":
            continue
        if len(held) >= cfg["max_pos"]:
            break
        if r["Sinyal"] == "-" or r["Hisse"] in held or r["Hisse"] in pending:
            continue
        qty = int(cfg["budget"] // r["Fiyat"])
        if qty < 1:
            log.append(f"{r['Hisse']}: bütçe yetmiyor ({r['Fiyat']}$)")
            continue
        t.submit_order(MarketOrderRequest(
            symbol=r["Hisse"], qty=qty, side=OrderSide.BUY, time_in_force=TimeInForce.DAY,
            order_class=OrderClass.BRACKET,
            take_profit=TakeProfitRequest(limit_price=r["Hedef"]),
            stop_loss=StopLossRequest(stop_price=r["Stop"])))
        held.add(r["Hisse"])
        msg = f"AL {r['Hisse']} x{qty} ~{r['Fiyat']}$ | stop {r['Stop']} | hedef {r['Hedef']} | {r['Sinyal']}"
        log.append(msg)
        notify(msg)
    return log or ["Sinyal yok, işlem yapılmadı."]


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

    st.title("📈 Lab Nasdaq")
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

    t_radar, t_rank, t_lab, t_perf, t_bot = st.tabs(["📡 Radar", "🏆 Sıralama", "🧪 Lab", "📊 Performans", "🤖 Bot"])

    with t_radar:
        st.caption("1 dk mum: hacim artışı + VWAP/EMA9 üstü + pozitif hacim deltası, henüz fırlamamış hisseler")
        if st.button("Yenile", key="r1"):
            st.cache_data.clear()
        with st.spinner("Taranıyor..."):
            rd = radar(wl)
        st.dataframe(rd, hide_index=True) if not rd.empty else st.info("Veri yok (piyasa kapalı olabilir).")

    with t_rank:
        with st.spinner("Hisseler analiz ediliyor..."):
            sc = scan(tuple(wl), tuple(cfg["strategies"]), stop, take)
        if sc.empty:
            st.info("Veri yok.")
        else:
            for _, r in sc.head(3).iterrows():
                if r.get("Durum") == "KIRILIM TEYİDİ / SANAL TEST":
                    st.success(f"**{r['Hisse']}** (sanal test) skor {r['Skor']} • Alış {r['Alış']} • Stop {r['Stop']} • "
                               f"Hedef {r['Hedef']} • Kırılım {r['Kırılım']}\n\n{r['Neden']}")
            st.dataframe(sc, hide_index=True)

    with t_lab:
        sym = st.selectbox("Hisse", wl)
        df = get_bars(sym, 10)
        if df is None:
            st.info("Veri yok.")
        else:
            rows = [{"Strateji": n, **stats(backtest(df, f(df), stop, take))} for n, f in STRATS.items()]
            st.dataframe(pd.DataFrame(rows), hide_index=True)
            pick = st.selectbox("Grafikte göster", list(STRATS))
            sig = STRATS[pick](df)
            lv = float(break_level(df).iloc[-1])
            p = float(df.close.iloc[-1])
            st.plotly_chart(chart(df, sig, [("Kırılım", lv, "#38bdf8"), ("Stop", p * (1 - stop / 100), "#ef4444"),
                                            ("Hedef", p * (1 + take / 100), "#22c55e")]))
            st.caption("Backtest son 10 gün, 5 dk mum, komisyon+kayma %0,1. Geçmiş sonuç geleceği garanti etmez.")

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

    with t_bot:
        st.write("Bot, **Sıralama** sinyallerine göre bracket emri (stop + hedef borsada) gönderir.")
        auto = st.toggle("Otomatik mod (sayfa açıkken her 5 dk)")
        st.session_state.setdefault("log", [])
        go_now = st.button("▶️ Şimdi tara ve işlem yap")
        if auto:
            from streamlit_autorefresh import st_autorefresh
            n = st_autorefresh(interval=300_000, key="tick")
            if n != st.session_state.get("last_tick"):
                st.session_state.last_tick = n
                go_now = True
        else:
            st.session_state.pop("last_tick", None)
        if go_now:
            try:
                for line in run_cycle(cfg):
                    st.session_state.log.insert(0, f"{datetime.now():%H:%M} {line}")
            except Exception as e:
                st.session_state.log.insert(0, f"{datetime.now():%H:%M} Hata: {e}")
        c1, c2 = st.columns(2)
        if c1.button("🛑 Hepsini sat (acil)"):
            tc().close_all_positions(cancel_orders=True)
            st.session_state.log.insert(0, f"{datetime.now():%H:%M} Acil kapatma yapıldı.")
            notify("Acil kapatma: tüm pozisyonlar satıldı.")
        if c2.button("🔔 Test bildirimi"):
            notify("Test: Lab Nasdaq bildirimi çalışıyor.")
            st.toast("Gönderildi (NTFY_TOPIC ayarlıysa)")
        st.text("\n".join(st.session_state.log[:30]) or "Kayıt yok.")
        st.caption("Otomatik mod, iPhone ekranı kilitlenince/sayfa kapanınca durur. Kesintisiz için GitHub Actions kullan.")


if "--worker" in sys.argv:
    worker()
else:
    ui()
