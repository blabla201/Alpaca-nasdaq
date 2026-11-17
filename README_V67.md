# Nasdaq Radar v6.7 — deneysel, yalnızca gözlem

## Değişiklikler
- Alpaca `movers` ve `most-actives` listelerinden isteğe bağlı aday keşfi. API erişimi veya liste güncelliği garanti edilmez. Kullanıcı onayıyla en çok 20 yeni hisse eklenir; toplam 35 hisse sınırı.
- Sıralama sekmesinde **Adayları ayrıntılı değerlendir**: kapanmış mum, veri yaşı, son 20 mum direnci, hacim oranı, VWAP/EMA9 ve dirençten fazla uzaklaşma kontrolleri. Spread/bid/ask yoksa kesin AL sinyali üretmez.
- Lab sekmesinde oturum bazlı gözlem günlüğü ve CSV dışa aktarımı; beş dakika sonraki ilk değerlendirmede **son gözlemin** değişimi hesaplanır, tam 5. dakika getirisi olarak yorumlanmamalıdır.
- API hataları yeni ayrıntılı değerlendirme tablosunda gösterilir; eski `scan()` fonksiyonu hata yutmaya devam edebilir.
- Eski stratejiler, backtest ve Radar sekmesi korunmuştur; bunların kârlılığı doğrulanmış değildir.

## Kurulum
ZIP içeriğini GitHub deposunun kök dizinine yükleyin; `app.py`, `radar_upgrade.py`, `requirements.txt` aynı seviyede olmalı. Streamlit Secrets'taki mevcut Alpaca anahtarlarını değiştirmeyin veya paylaşmayın. Yeni bağımlılık yoktur.

## Sınırlar
- Gerçek zamanlı WebSocket **eklenmedi**. Streamlit Cloud'da kalıcı arka plan taraması ve push bildirim **eklenmedi**.
- Alpaca ücretsiz IEX verisi tüm ABD piyasasını kapsamaz. Screener listesi anlık kırılım garantisi değildir.
- Pre-market mum analizi **henüz eklenmedi**; mevcut `get_bars()` normal seansla sınırlı.
- Bid/ask spread, işlem derinliği, tam işlem maliyetleri **henüz eklenmedi**.
- Sinyal günlüğü kalıcı değildir ve ileriye dönük başarı oranı için yeterli altyapı değildir.
- Gerçek emir veya otomatik paper emir **gönderilmez**.

## Test
`python -m unittest discover -s tests -v` (pandas ve numpy gerekir). Bu testler sentetik veri üzerinde fonksiyon davranışını denetler; canlı Alpaca erişimini, finansal performansı veya Streamlit Cloud dağıtımını doğrulamaz.
