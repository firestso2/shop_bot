"""Центральный конфиг. Все настройки только здесь."""

# ── Бот ─────────────────────────────────────────────────────────────────────
BOT_TOKEN = "8720299373:AAFKATspEk-A76AXSS18SPP8GL3NX4jtA_o"
ADMIN_IDS = [6595541980, 8366926831, 8416449434]

# ── Каналы ──────────────────────────────────────────────────────────────────
OP_CHANNEL     = "@NotWork3rNews"
REVIEW_CHANNEL = "@chat_vorache777"

# ── Контакты ─────────────────────────────────────────────────────────────────
OWNER_USERNAME   = "vorache777"
SUPPORT_USERNAME = "notwork3r"

# ── PostgreSQL ───────────────────────────────────────────────────────────────
DB_DSN = "postgresql://user:password@localhost:5432/shopbot"

# ── Redis (FSM storage + TTL сессий) ─────────────────────────────────────────
REDIS_DSN     = "redis://localhost:6379/0"
FSM_TTL_SEC   = 1800   # 30 минут — после этого незавершённая сессия сбрасывается

# ── Webhook ───────────────────────────────────────────────────────────────────
WEBHOOK_BASE_URL  = "https://your-domain.com"   # публичный домен
WEBHOOK_BOT_PATH  = "/bot/webhook"              # путь для Telegram
WEBHOOK_HOST      = "0.0.0.0"
WEBHOOK_PORT      = 8443                        # порт, который слушает aiohttp

# ── Платёжные системы ────────────────────────────────────────────────────────
CRYPTOBOT_TOKEN   = "554526:AA3lwCzWXKNkEvRNIqoIjm4kIp9JKcWZuJV"
CRYPTOBOT_API     = "https://pay.crypt.bot/api"
CRYPTOBOT_DIVISOR = 0.97   # пользователь платит amount / 0.97, зачисляется amount

FREEKASSA_SHOP_ID  = "YOUR_FK_SHOP_ID"
FREEKASSA_SECRET1  = "YOUR_FK_SECRET1"
FREEKASSA_SECRET2  = "YOUR_FK_SECRET2"
FREEKASSA_CURRENCY = "RUB"
FREEKASSA_WEBHOOK_PATH = "/fk/webhook"
# Курс FK: захардкожен, без внешних API
FREEKASSA_RATE_RUB_PER_USD = 85.0   # 85 рублей = 1 доллар

# ── Telegram Stars ───────────────────────────────────────────────────────────
# Захардкожен, без внешних API
STARS_USD_PER_STAR = 0.014   # 1 звезда = 0.014 USD
STARS_RATE = 0.014

# ── Реферальная система ──────────────────────────────────────────────────────
REFERRAL_PERCENT = 5
MIN_TOPUP        = 1.0

# ── Оптовая скидка ───────────────────────────────────────────────────────────
BULK_MIN_QTY      = 3
BULK_DISCOUNT_PCT = 5.0

# ── Пагинация каталога ────────────────────────────────────────────────────────
CATALOG_PAGE_SIZE = 10   # товаров на страницу в каталоге

# ── P2P чат (заказы с данными) ────────────────────────────────────────────────
ORDER_AUTO_CANCEL_HOURS = 6      # автовозврат если никто не взял / не завершил
ORDER_EXTEND_HOURS      = 2      # на сколько продлевает «Продлить время»

# ── Автопроверка платежей ─────────────────────────────────────────────────────
PAYMENT_CHECK_INTERVAL = 30   # секунд

# ── Уведомление об остатках ──────────────────────────────────────────────────
LOW_STOCK_THRESHOLD = 3

# ── Антиспам ─────────────────────────────────────────────────────────────────
SPAM_COOLDOWN = 3

# ── Резервное копирование ────────────────────────────────────────────────────
BACKUP_INTERVAL_HOURS = 6
BACKUP_DIR = "backups"

# ── Логирование ──────────────────────────────────────────────────────────────
LOG_FILE = "bot.log"
