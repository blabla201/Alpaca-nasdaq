# Nasdaq Radar v6.6 — ölçüm ve güvenli test

## Değişiklikler
- 1 dakikalık IEX verisi; son tamamlanmamış mum dışlanır.
- Radar 15dk değişimi artık gerçekten 15 dakikalık kesintisiz 16 mumla hesaplar; yoksa boş bırakır.
- Lab backtest sonraki mum açılışından girer; stop/hedef aynı mumda görülürse stop öncelikli; açılış gap'i hesaba katılır.
- Varsayılan %0,20 gidiş-dönüş maliyet varsayımı (gerçek spread/komisyon değil).
- Teyit yalnızca seçili stratejinin son mum sinyalinden, hacim ve trend koşullarıyla gelir.
- Otomatik emir, acil kapatma ve GitHub Actions zamanlanmış emir işlevleri devre dışı.
- Radar kapanış sonrası eski fiyatları canlı sinyal diye sunmaz.

## Önemli sınırlar
- IEX tüm ABD borsası değildir. REST sorgusu tüm piyasayı anlık izleyemez.
- Gerçek 1dk scalping için bid/ask, veri bütünlüğü, gecikme, likidite ve forward-test gerekir.
- Bu sürümün kârlılığı kanıtlanmadı. Yeni strateji değil, ölçüm/güvenlik iyileştirmesidir.
- Streamlit Secrets'taki anahtarları hiçbir dosyaya eklemeyin.
