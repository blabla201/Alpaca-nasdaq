# Nasdaq Radar v6.5 — Trend + Pullback (deneysel)
Fotoğraftaki MQL5 EMA20/EMA50 trend + pullback + engulfing kuralları Python/Streamlit'e uyarlandı; MT5/MQL5 kurulu değildir.
- 1 dakikalık IEX mumları, EMA20 > EMA50, son beş önceki mumda EMA bandına temas, son kapanmış mumda bullish engulfing.
- Swing dip veya 1,5 ATR stop; örnek 2R hedef. Bunlar kâr tahmini değildir.
- Lab sekmesinde strateji karşılaştırması ve stop yöntemi seçimi.
- Sıralama ekranında sinyal teyidi, Radar'da eski veri için uyarı.
- Paper emirler varsayılan kapalıdır; gerçek emir gönderilmez.
- Veriler yalnızca IEX; likidite ve spread filtreleri henüz yok. Canlı piyasada ve geçmiş verilerle doğrulanmadı.
