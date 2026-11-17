# Nasdaq Radar v7.1 — Hata düzeltme paketi

Bu sürüm önceki v7.0.1 kaynaklarından oluşturulmuştur.

## Düzeltilenler
- `scan()` fonksiyonu `scan_stocks()` olarak yeniden adlandırıldı; keşif bölümündeki `scan` sözlüğüyle isim çakışması giderildi.
- Hem Sıralama hem Bot sekmelerindeki çağrılar güncellendi.
- Radar sekmesinde tek sembolde Alpaca veri hatası tüm uygulamayı durdurmaz.
- Ekran başlığı v7.1 olarak güncellendi.
- Başlangıç listesindeki RIOT ve SNAP korundu.

## Kurulum
GitHub deposunda ZIP içindeki **dosyaları ve klasörleri** mevcut kök dizine yükleyin. ZIP dosyasını tek başına GitHub'a yüklemek uygulamayı güncellemez. `app.py` kökte bulunmalıdır. `discovery_engine.py`, `breakout_engine.py`, `radar_upgrade.py`, `radar_quality.py` aynı dizinde olmalıdır. Streamlit Secrets içindeki anahtarları değiştirmeyin.

## Güvenlik ve sınırlamalar
Otomatik emir gönderimi kapalıdır. Kodun sözdizimi ve yerel testleri kontrol edilmiştir; canlı Alpaca erişimi, Streamlit Cloud dağıtımı ve kazanç başarısı doğrulanmamıştır. IEX verisi tüm ABD borsalarının birleşik akışı değildir.
