# Alpaca Nasdaq — Telegram bağlantısı

Streamlit Cloud > Settings > Secrets bölümünde aşağıdaki anahtarlar bulunmalı:

```toml
TELEGRAM_BOT_TOKEN = "BotFather gizli token"
TELEGRAM_CHAT_ID = "Telegram kullanıcı ID"
```

Uygulamayı açın, **Telegram bildirimleri** bölümünden **Telegram test mesajı gönder** düğmesine basın. Ardından mevcut radar ön adaylarını manuel olarak Telegram'a gönderebilirsiniz.

**Sınır:** Bu sürümde Telegram bildirimleri yalnızca uygulamadaki düğmeye basıldığında gönderilir. Streamlit'in kapalı uygulamayı sürekli çalıştırdığı varsayılmaz. iPhone kilitliyken bağımsız ve sürekli bildirim için ayrıca zamanlanmış bir worker ve güvenli kimlik bilgisi kurulumu gerekir. Otomatik emirler kapalıdır.
