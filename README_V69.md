# Nasdaq Radar v6.9 — Birleşik Kırılım Motoru

Bu sürüm, v6.8'in üzerine eklenmiştir. `breakout_engine.py` dosyası mutlaka `app.py` ile aynı dizinde olmalıdır.

## Kırılım kuralları
- Yalnızca kapanmış normal seans 1 dakika mumları, aynı seanstaki önceki 20 mumun en yüksek fiyatı dirençtir.
- Son kapanış önceki direncin altında/eşitken yeni kapanışın direnç üstüne çıkması gerekir.
- Kapanış, direncin ATR'ye bağlı %0,05–%0,30 tamponunun üstünde olmalı.
- Hacim son 20 mum ortalamasının en az 1,5 katı; pozitif mum gövdesi mum aralığının en az %50'si.
- Dirençten %1,2'den fazla uzaklaşmış yeni geçiş 'geç kırılım' olarak işaretlenir.
- Direncin %0,75 altında veya daha yakın ancak geçilmemişse 'dirence yakın'; daha uzaktaysa 'dirence uzak'.
- 3 dakikadan eski veri, eksik mumlar ve yeterli seans verisi olmayan hisseler reddedilir.
- EMA pullback tek başına teyitli kırılım olarak değerlendirilmez.

## Sınırlar
Bu formül bir araştırma hipotezidir, kârlılığı kanıtlanmamıştır. Alpaca IEX verisi tam piyasa verisi değildir. Bid/ask ve gerçek emir gerçekleşmesi doğrulanmadan gerçek alım yapılmamalıdır. Kod sentetik birim testlerinden geçirilmiştir; canlı Alpaca testi yapılmamıştır. Diğer stratejiler ve eski Radar ekranı korunmuştur; Sıralama ve Lab kırılım sinyali güncellenmiştir.
