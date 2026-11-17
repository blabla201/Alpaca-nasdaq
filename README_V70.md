# Nasdaq Radar v7.0 — Denetlenebilir Keşif

## Değişiklikler
- Alpaca movers ve most-actives sorgularından gelen sembolleri Alpaca paper trading assets metadata ile doğrular. Aktif, tradable, US equity ve tanımlanmış borsa koşullarını arar; warrant, unit, right, preferred, note, bond adlarını eler.
- Yeni/çıkan/aynı sembolleri karşılaştırır; tarama zamanını UTC olarak gösterir.
- Elenenleri ve API hatalarını görünür kılar; keşif geçmişini oturum boyunca tutar ve CSV indirir.
- Asset listesi 1 saat önbellekte tutulur; screener her düğme basışında yeniden sorgulanır.
- Önceki v6.9 kırılım ve kalite modülleri korunur. Otomatik emir çalıştırma değiştirilmedi; PAPER=True.

## Sınırlar
- Bu sürüm TÜM NASDAQ hisselerini taramaz. Alpaca'nın iki hazır screener listesini kullanır. Seans kapalıyken listeler değişmeyebilir; aynı semboller görülmesi tek başına hata değildir.
- Hisse keşfi ve karşılaştırma geçmişi Streamlit oturumuna bağlıdır; yeniden başlatınca sıfırlanır.
- Alpaca Paper assets endpoint'i erişilemezse güvenlik nedeniyle keşfedilen semboller kabul edilmez; ekranda hata gösterilir.
- Alpaca IEX ücretsiz akışının kapsamı sınırlıdır. Canlı Alpaca hesabı ile doğrulanmadı.
- Sinyaller gerçek işlem önerisi değildir.

## Kurulum
ZIP içeriğini GitHub deposunun kök dizinine yükleyin. app.py ile discovery_engine.py aynı dizinde olmalıdır. Mevcut Streamlit Secrets değişmez. `python -m unittest discover -s tests` ile test edin.
