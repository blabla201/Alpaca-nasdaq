# Lab Nasdaq v6.4 — güvenli test sürümü
- 1 dakikalık Alpaca IEX mumları kullanır; veri en fazla 2 dakika eski olabilir.
- Skor 0–100 ile sınırlandırılır, yalnızca son kapanmış mumun sinyali dikkate alınır.
- Kırılım doğrulanmadığında "İZLE" olarak etiketler.
- GitHub Actions zamanlanmış otomatik emirleri kapalıdır. Paper emirleri varsayılan kapalıdır.
- Streamlit Secrets: ALPACA_KEY / ALPACA_SECRET veya ALPACA_API_KEY / ALPACA_SECRET_KEY.
- IEX tüm ABD piyasası değildir; 1 dakikalık gerçek işlem için doğrulanmış tam piyasa verisi ve bid/ask gerekir.
- Sinyallerin başarı oranı ölçülmemiştir. Canlı işlem yapmayın.
