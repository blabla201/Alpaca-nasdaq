"""GitHub Actions scheduled, read-only IEX momentum watcher. No trading endpoints."""
import os
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import requests
from discovery_engine import fetch_candidates, fetch_asset_map

BASE = "https://data.alpaca.markets/v2"
NY = ZoneInfo("America/New_York")
DEFAULT_SYMBOLS = "SOFI,F,PLUG,SNAP,RIOT,NIO,LCID,HOOD,PLTR,AMD,FRTT,GP"
MAX_DISCOVERED = 20
MAX_TOTAL = 35


def market_open(now):
    local = now.astimezone(NY)
    minutes = local.hour * 60 + local.minute
    return local.weekday() < 5 and 570 <= minutes < 960


def symbols_from_env():
    raw = os.environ.get("WATCHLIST", DEFAULT_SYMBOLS)
    return list(dict.fromkeys(x.strip().upper() for x in raw.split(",") if x.strip()))[:35]


def build_universe(session, key, secret):
    """Merge the fixed watchlist with verified live Alpaca screener discoveries.

    Discovery failure does not prevent monitoring the fixed list.
    """
    fixed = symbols_from_env()
    try:
        assets = fetch_asset_map(key, secret, get=session.get)
        discovery = fetch_candidates(key, secret, limit=MAX_DISCOVERED,
                                     asset_map=assets, get=session.get)
        for error in discovery.get('errors', []):
            print('Keşif uyarısı: ' + str(error)[:180])
        discovered = discovery.get('symbols', [])[:MAX_DISCOVERED]
    except (requests.RequestException, ValueError, TypeError, KeyError) as exc:
        print(f'Keşif başarısız ({type(exc).__name__}); sabit listeyle devam ediliyor.')
        discovered = []
    merged = list(dict.fromkeys(fixed + discovered))[:MAX_TOTAL]
    print(f'Sabit liste: {len(fixed)} | Keşfedilen: {len(discovered)} | Tekil tarama: {len(merged)}')
    return merged


def get_bars(session, symbol, now):
    headers = {"APCA-API-KEY-ID": os.environ["ALPACA_KEY"], "APCA-API-SECRET-KEY": os.environ["ALPACA_SECRET"]}
    response = session.get(f"{BASE}/stocks/{symbol}/bars", headers=headers, params={
        "timeframe": "1Min", "start": (now-timedelta(hours=3)).isoformat().replace("+00:00", "Z"),
        "end": now.isoformat().replace("+00:00", "Z"), "limit": 200, "feed": "iex", "adjustment": "raw"
    }, timeout=15)
    response.raise_for_status()
    return response.json().get("bars") or []


def analyze(bars, now):
    # Only closed bars from the current NY regular session; reject stale quotes.
    today = now.astimezone(NY).date()
    valid = []
    for bar in bars:
        t = datetime.fromisoformat(bar["t"].replace("Z", "+00:00"))
        local = t.astimezone(NY)
        if local.date() == today and 570 <= local.hour*60+local.minute < 960 and t + timedelta(minutes=1) <= now:
            valid.append((t, bar))
    if len(valid) < 32:
        return None
    t, last = valid[-1]
    if (now-(t+timedelta(minutes=1))).total_seconds() > 150:
        return None
    closes = [float(x[1]["c"]) for x in valid]
    vols = [float(x[1]["v"]) for x in valid]
    highs = [float(x[1]["h"]) for x in valid]
    lows = [float(x[1]["l"]) for x in valid]
    price = closes[-1]
    if price <= 0:
        return None
    ema = closes[0]
    for p in closes[1:]:
        ema = (2/10)*p + (8/10)*ema
    typical = [(highs[i]+lows[i]+closes[i])/3 for i in range(len(closes))]
    total_volume = sum(vols)
    vwap = sum(p*v for p,v in zip(typical,vols))/total_volume if total_volume else 0
    prev_vol = sum(vols[-21:-1])/20
    rvol = vols[-1]/prev_vol if prev_vol else 0
    resistance = max(highs[-21:-1])
    change15 = (price/closes[-16]-1)*100
    day_change = (price/float(valid[0][1]["o"])-1)*100
    # Pre-candidate: positive momentum with relative volume, not a buy signal.
    candidate = (price > ema and price > vwap and rvol >= 1.8 and 0.3 <= change15 <= 3 and day_change < 6)
    # Breakout: price crosses 20-bar resistance, with stronger volume.
    breakout = (price > resistance and closes[-2] <= max(highs[-22:-2]) and rvol >= 2 and price > vwap and price > ema)
    if not (candidate or breakout):
        return None
    return {"status": "KIRILIM TAKIBI" if breakout else "ON ADAY", "price": price, "rvol": rvol,
            "change15": change15, "resistance": resistance, "bar_time": t.astimezone(NY).strftime("%H:%M")}


def send(session, token, chat_id, msg):
    response = session.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": chat_id, "text": msg}, timeout=15)
    response.raise_for_status()
    if not response.json().get("ok"):
        raise RuntimeError("Telegram mesajı onaylamadı")


def main():
    required = ["ALPACA_KEY", "ALPACA_SECRET", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]
    missing = [x for x in required if not os.environ.get(x)]
    if missing:
        print("GitHub Actions Secrets eksik: " + ", ".join(missing)); return 2
    now = datetime.now(timezone.utc)
    if not market_open(now):
        print("ABD normal seansı dışında; uyarı gönderilmedi."); return 0
    session = requests.Session()
    found = []
    for symbol in build_universe(session, os.environ["ALPACA_KEY"], os.environ["ALPACA_SECRET"]):
        try:
            result = analyze(get_bars(session,symbol,now),now)
            if result:
                found.append((symbol,result))
        except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
            print(f"{symbol}: veri alınamadı ({type(exc).__name__})")
    if not found:
        print("Yeni eşik üstü sinyal yok."); return 0
    # Batch alerts, maximum one Telegram message per execution. Each run may repeat signals.
    lines = ["📈 ALPACA NASDAQ — Otomatik izleme", "⚠️ İzleme sinyali; alım tavsiyesi değildir.", "Sabit liste + Alpaca hareketli hisseler keşfi; IEX verisi, yalnızca normal seans.", ""]
    for symbol,r in found[:12]:
        lines.append(f"{symbol} | {r['status']} | ${r['price']:.2f} | 15dk %{r['change15']:.1f} | Hacim {r['rvol']:.1f}x | {r['bar_time']} NY")
    send(session,os.environ["TELEGRAM_BOT_TOKEN"],os.environ["TELEGRAM_CHAT_ID"],"\n".join(lines))
    print(f"{len(found)} sinyal için tek Telegram mesajı gönderildi.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
