# ⚙️ Руководство по развёртыванию

---

## 1. Зависимости на сервере (Ubuntu 22.04)

```bash
apt update && apt upgrade -y
apt install python3.11 python3.11-pip python3.11-venv \
            postgresql postgresql-contrib redis-server nginx certbot \
            python3-certbot-nginx -y
```

---

## 2. PostgreSQL

```bash
sudo -u postgres psql
```

```sql
CREATE USER shopbot WITH PASSWORD 'yourpassword';
CREATE DATABASE shopbot OWNER shopbot;
\q
```

В `config.py`:
```python
DB_DSN = "postgresql://shopbot:yourpassword@localhost:5432/shopbot"
```

---

## 3. Redis

Запускается автоматически после установки. Проверить:
```bash
redis-cli ping
# PONG
```

В `config.py`:
```python
REDIS_DSN   = "redis://localhost:6379/0"
FSM_TTL_SEC = 1800   # 30 минут — сессия сбрасывается если нет активности
```

---

## 4. SSL и Nginx

```bash
# Получить сертификат
certbot --nginx -d your-domain.com

# Скопировать конфиг
cp nginx.conf /etc/nginx/sites-available/shopbot
ln -s /etc/nginx/sites-available/shopbot /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
```

Замените `your-domain.com` на ваш реальный домен.

---

## 5. Виртуальное окружение и зависимости

```bash
cd /root/shop_bot
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## 6. config.py — что заполнить обязательно

```python
BOT_TOKEN         = "токен от @BotFather"
ADMIN_IDS         = [ваш_telegram_id]
DB_DSN            = "postgresql://shopbot:pass@localhost:5432/shopbot"
REDIS_DSN         = "redis://localhost:6379/0"
WEBHOOK_BASE_URL  = "https://your-domain.com"   # ← ваш домен с HTTPS

CRYPTOBOT_TOKEN   = "токен от @CryptoBot"
FREEKASSA_SHOP_ID = "ID магазина в FK"
FREEKASSA_SECRET1 = "Секрет 1"
FREEKASSA_SECRET2 = "Секрет 2"
```

Курсы валют (не менять без нужды):
```python
FREEKASSA_RATE_RUB_PER_USD = 85.0   # 85 ₽ = 1 $
STARS_USD_PER_STAR          = 0.014  # 1 ⭐ = 0.014 $
```

---

## 7. FreeKassa — настройка уведомлений

В личном кабинете FreeKassa укажи URL уведомлений:
```
https://your-domain.com/fk/webhook
```

---

## 8. Запуск

```bash
source venv/bin/activate
python main.py
```

Для фонового режима через supervisor:
```bash
apt install supervisor -y
nano /etc/supervisor/conf.d/shopbot.conf
```

```ini
[program:shopbot]
command=/root/shop_bot/venv/bin/python /root/shop_bot/main.py
directory=/root/shop_bot
autostart=true
autorestart=true
stderr_logfile=/var/log/shopbot.err.log
stdout_logfile=/var/log/shopbot.out.log
user=root
```

```bash
supervisorctl reread && supervisorctl update && supervisorctl start shopbot
supervisorctl status shopbot   # → RUNNING
```

---

## 9. Проверка

1. Напишите боту `/start`
2. Должно появиться приветствие с inline-кнопками
3. Проверьте `/admin` — должна открыться панель
4. Попробуйте пополнить баланс через CryptoBot

---

## Команды после запуска

```bash
# Статус
supervisorctl status shopbot

# Перезапустить после изменений
supervisorctl restart shopbot

# Логи ошибок
tail -f /var/log/shopbot.err.log

# Логи бота
tail -f /root/shop_bot/bot.log
```

---

## Архитектура webhook

```
Telegram → HTTPS → Nginx (443) → aiohttp (8443)
FreeKassa → HTTPS → Nginx (443) → aiohttp (8443) /fk/webhook
```

Nginx завершает TLS и проксирует на локальный порт 8443.
Бот слушает только на 127.0.0.1:8443 (не доступен снаружи напрямую).
