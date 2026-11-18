# Alpaca Nasdaq v7.3 — otomatik Telegram hazırlığı

Bu paket v7.2 Streamlit uygulamasını korur, ayrıca `auto_alert_worker.py` ve `.github/workflows/telegram_alerts.yml` ekler. İşlem emri göndermez.

## ÖNEMLİ: Streamlit Secrets, GitHub Actions'a otomatik aktarılmaz.
GitHub deposu > Settings > Secrets and variables > Actions > New repository secret yoluyla şu DÖRT değeri ayrı ayrı tanımlayın: `ALPACA_KEY`, `ALPACA_SECRET`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`. Token'ları sohbet içinde paylaşmayın. Telegram kullanıcı ID'si özel bot sohbetlerinde genellikle Chat ID olarak çalışır.

GitHub > Actions > Alpaca Nasdaq otomatik Telegram izleme > Run workflow ile test edin. ABD normal seansı dışında test yapılırsa bilerek mesaj gönderilmez. Workflow varsayılan dalda bulunmalıdır. GitHub Actions ayarları etkin olmalıdır.

İzleme, hafta içi yaklaşık 5 dakikada bir tetiklenmek üzere ayarlanmıştır; GitHub zamanlaması gecikebilir veya atlanabilir. Resmî ABD piyasa tatillerinde yeterli güncel mum bulunmazsa uyarı çıkmaz. ABD normal seansı New York saati 09:30-16:00 arasında kontrol edilir; premarket dahil değildir. Alpaca IEX ücretsiz veri akışı tüm borsa işlemlerini kapsamaz. Varsayılan liste: SOFI,F,PLUG,SNAP,RIOT,NIO,LCID,HOOD,PLTR,AMD,FRTT,GP. `WATCHLIST` GitHub Actions repository variable ile değiştirilebilir. Bu sabit listeye Alpaca movers (yükselenler/düşenler) ve most-actives kaynaklarından doğrulanmış en fazla 20 hisse eklenir. Tekil tarama üst sınırı 35 hissedir. Keşif başarısız olursa sabit liste taranmaya devam eder. Bu yöntem tüm Nasdaq hisselerini kapsamlı olarak taramaz.

**Sınırlamalar:** Aynı sinyal sonraki çalıştırmalarda yeniden gelebilir; kalıcı tekilleştirme henüz yoktur. İlk kurulumdan sonra ABD seansında gerçek Telegram uyarısı test edilmelidir. Yazılımın kazanç sağladığı iddia edilmez. Program otomatik emir göndermez.

## v7.4 Dinamik keşif
Her zamanlanmış çalışmada, sabit listenin yanına Alpaca screener hareketli ve en aktif hisse listeleri eklenir. Aktif, işlem yapılabilir adi hisseler asset bilgisiyle doğrulanır. Her hissede güncel 1 dakikalık IEX mumları, hacim ve kırılım eşikleri değerlendirilir. Keşfedilmek tek başına Telegram mesajı üretmez; teknik eşik geçilmelidir. GitHub Actions gecikmeleri, 1 dakikalık veri kapsamı ve tekrar mesaj sınırlaması devam eder. Gizli anahtarları ZIP içine koymayın.
