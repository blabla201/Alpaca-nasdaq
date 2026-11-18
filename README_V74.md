# Alpaca Nasdaq v7.4 — Sabit liste + otomatik keşif

- GitHub Actions zamanlayıcısı ABD normal seansında yaklaşık her 5 dakikada bir çalışacak şekilde yapılandırılmıştır; garanti edilen zamanlama değildir.
- Sabit liste ve Alpaca screener movers / most-actives birleşimi taranır (en çok 35 tekil hisse).
- Keşif için aktif ve işlem yapılabilir adi hisse kontrolü yapılır; API hatasında sabit liste korunur.
- Telegram mesajı yalnızca 1 dakikalık IEX verisinde momentum veya kırılım koşulları gerçekleşirse gönderilir.
- GitHub > Settings > Secrets and variables > Actions: ALPACA_KEY, ALPACA_SECRET, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID gereklidir. Streamlit Secrets otomatik aktarılmaz.
- GitHub > Actions > Alpaca Nasdaq otomatik Telegram izleme > Run workflow ile elle test edebilirsiniz; seans dışında mesaj gelmemesi normaldir.
- Otomatik emir yoktur. Kalıcı tekrar bildirim engelleme henüz yoktur; mesajlar tekrarlanabilir.
