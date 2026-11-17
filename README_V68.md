# Nasdaq Radar v6.8 — Doğrulama Radarı

Bu sürüm v6.7 üzerine kurulmuştur. Bir kâr tahmin modeli veya otomatik işlem botu değildir. **Gerçek veya paper emir göndermez.**

## Değişiklikler
- `radar_quality.py`: ayrı test edilebilir kalite motoru; yalnızca kapanmış 1dk mum; seans, veri yaşı ve eksik mum kontrolü; IEX quote ile spread kontrolü; eksik/eski quote durumunda hiçbir zaman işlem adayı sinyali üretmez.
- `app.py`: `🛡️ Kalite & Kayıt` sekmesi, doğrulama tablosu, neden işlem yapılmadığı açıklaması ve indirilebilir CSV.
- İleriye dönük gözlem kaydı: 1/5/10/30 dakika sonra **tam o dakika** kapanmış bar varsa ölçüm. Yoksa boş bırakılır. Bu bir işlem getirisi veya backtest değildir.
- Önceki Lab bölümündeki %0,20 varsayılan toplam işlem maliyetinin açıklaması düzeltildi.

## Kurulum
v6.7 dosyalarının tamamını bu ZIP ile değiştirin; `app.py`, `radar_upgrade.py`, `radar_quality.py`, `requirements.txt` aynı dizinde olsun. Streamlit Secrets içinde mevcut ALPACA_KEY ve ALPACA_SECRET (veya alternatif anahtar adları) kalabilir. Anahtarları GitHub'a yüklemeyin.

## Kullanım
1. Normal piyasa seansında uygulamayı açın.
2. Yeni adayları keşfet'e basın. Bu Alpaca screener erişimine bağlıdır ve geniş piyasanın eksiksiz taraması değildir.
3. `Kalite & Kayıt` sekmesinde `Güncel adayları doğrula`ya basın. Bid/ask bulunamazsa AL sonucu gösterilmez.
4. En az 1/5/10/30 dakika sonra `Sinyal sonuçlarını ölç`e basın ve CSV'yi indirin. Streamlit oturum belleği kalıcı değildir.

## Bilinen sınırlar
- Alpaca IEX verisi konsolide ABD piyasa akışı değildir; hacim ve kotasyon eksik olabilir.
- Bu sürümde WebSocket, geniş evrenin tamamını otomatik izleme, kalıcı veritabanı, pre-market sinyali, gerçekçi emir defteri simülasyonu ve bağımsız canlı performans doğrulaması YOKTUR.
- `Sıralama` ve `Radar` eski deneysel sekmeler olarak durur; `Kalite & Kayıt` sekmesi daha katı kontrol uygular. Eski skorlara güvenerek işlem yapmayın.
- Geçmiş 10 günlük testler, küçük örnek ve örnekleme yanlılığı nedeniyle kârlılık kanıtı değildir.

## Doğrulama
`python -m unittest discover -s tests -v` — 9 test başarılı (sentetik veriler). Python sözdizimi kontrolü başarılı. Gerçek Alpaca hesabıyla entegrasyon testi yapılmadı.
