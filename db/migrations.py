"""
SQL-схема PostgreSQL. Выполняется при старте — идемпотентно.
"""

SCHEMA = """
PRAGMA_COMPAT:
-- ═══════════════════════════════════════════════════════════
--  ПОЛЬЗОВАТЕЛИ
-- ═══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS users (
    id            BIGINT PRIMARY KEY,
    username      TEXT          NOT NULL DEFAULT '',
    balance       NUMERIC(12,4) NOT NULL DEFAULT 0,
    referrer_id   BIGINT        REFERENCES users(id),
    ref_earned    NUMERIC(12,4) NOT NULL DEFAULT 0,
    is_subscribed BOOLEAN       NOT NULL DEFAULT FALSE,
    joined_at     TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

-- ═══════════════════════════════════════════════════════════
--  КАТЕГОРИИ (рекурсивные, любая глубина)
-- ═══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS categories (
    id        SERIAL PRIMARY KEY,
    name      TEXT NOT NULL,
    parent_id INT  REFERENCES categories(id)
);

-- ═══════════════════════════════════════════════════════════
--  ТОВАРЫ
-- ═══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS products (
    id                SERIAL PRIMARY KEY,
    category_id       INT           NOT NULL REFERENCES categories(id),
    name              TEXT          NOT NULL,
    description       TEXT,
    price             NUMERIC(12,4) NOT NULL,
    status            TEXT          NOT NULL DEFAULT 'draft'
                                    CHECK(status IN ('active','draft')),
    needs_data        BOOLEAN       NOT NULL DEFAULT FALSE,
    data_request_text TEXT,
    instruction_text  TEXT,
    instruction_file  TEXT,
    bulk_discount_pct NUMERIC(5,2)  NOT NULL DEFAULT 5,
    bulk_min_qty      INT           NOT NULL DEFAULT 3
);

-- ═══════════════════════════════════════════════════════════
--  ЕДИНИЦЫ ТОВАРА (с группами файлов)
-- ═══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS items (
    id         SERIAL  PRIMARY KEY,
    product_id INT     NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    content    TEXT    NOT NULL,
    type       TEXT    NOT NULL DEFAULT 'text'
                       CHECK(type IN ('text','link','file')),
    item_group INT     NOT NULL DEFAULT 0,
    is_sold    BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS idx_items_product ON items(product_id, is_sold, item_group);

-- ═══════════════════════════════════════════════════════════
--  ПЛАТЕЖИ
-- ═══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS payments (
    id          SERIAL PRIMARY KEY,
    user_id     BIGINT        NOT NULL REFERENCES users(id),
    amount      NUMERIC(12,4) NOT NULL,
    credited    NUMERIC(12,4) NOT NULL,
    method      TEXT          NOT NULL,
    external_id TEXT          UNIQUE,
    status      TEXT          NOT NULL DEFAULT 'pending'
                              CHECK(status IN ('pending','paid','failed')),
    created_at  TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_payments_ext ON payments(external_id) WHERE status='pending';

-- ═══════════════════════════════════════════════════════════
--  ЗАКАЗЫ
-- ═══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS orders (
    id            SERIAL PRIMARY KEY,
    order_code    TEXT          NOT NULL UNIQUE,
    user_id       BIGINT        NOT NULL REFERENCES users(id),
    product_id    INT           NOT NULL REFERENCES products(id),
    quantity      INT           NOT NULL,
    total         NUMERIC(12,4) NOT NULL,
    discount_pct  NUMERIC(5,2)  NOT NULL DEFAULT 0,
    coupon_code   TEXT,
    -- pending | waiting_confirm | in_work | completed | cancelled
    status        TEXT          NOT NULL DEFAULT 'pending',
    user_data     TEXT,
    -- Для Stars: telegram charge_id для возврата
    stars_charge_id TEXT,
    -- Кто из админов взял заказ
    assigned_admin  BIGINT,
    -- Когда взяли (для автовозврата по таймеру)
    taken_at        TIMESTAMPTZ,
    -- Дедлайн: автовозврат если не завершён до этого времени
    deadline        TIMESTAMPTZ,
    created_at    TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_orders_user   ON orders(user_id);
CREATE INDEX IF NOT EXISTS idx_orders_code   ON orders(order_code);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_admin  ON orders(assigned_admin) WHERE assigned_admin IS NOT NULL;

-- ═══════════════════════════════════════════════════════════
--  P2P ЧАТ: связь сообщений бот↔юзер↔админ
--  Хранит message_id в чате бота для возможности reply/edit
-- ═══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS p2p_messages (
    id           BIGSERIAL PRIMARY KEY,
    order_code   TEXT      NOT NULL REFERENCES orders(order_code) ON DELETE CASCADE,
    from_user    BOOLEAN   NOT NULL,  -- TRUE = от юзера, FALSE = от админа
    tg_msg_id    BIGINT    NOT NULL,  -- msg_id в чате отправителя
    fwd_msg_id   BIGINT,              -- msg_id в чате получателя (для обратной связи)
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_p2p_order ON p2p_messages(order_code);

-- ═══════════════════════════════════════════════════════════
--  КУПОНЫ
-- ═══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS coupons (
    code        TEXT PRIMARY KEY,
    type        TEXT          NOT NULL DEFAULT 'percent'
                              CHECK(type IN ('percent','fixed')),
    value       NUMERIC(12,4) NOT NULL,
    max_uses    INT           NOT NULL DEFAULT 0,
    expire_at   TIMESTAMPTZ,
    created_at  TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS coupon_uses (
    coupon_code TEXT    NOT NULL REFERENCES coupons(code) ON DELETE CASCADE,
    user_id     BIGINT  NOT NULL REFERENCES users(id),
    used_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (coupon_code, user_id)
);

-- ═══════════════════════════════════════════════════════════
--  ПОДПИСКИ НА УВЕДОМЛЕНИЯ О ПОСТУПЛЕНИИ
-- ═══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS stock_notify (
    user_id    BIGINT NOT NULL REFERENCES users(id),
    product_id INT    NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, product_id)
);

-- ═══════════════════════════════════════════════════════════
--  ЛОГ ДЕЙСТВИЙ
-- ═══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS audit_log (
    id         BIGSERIAL PRIMARY KEY,
    user_id    BIGINT,
    action     TEXT        NOT NULL,
    details    JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_audit_user   ON audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action);
CREATE INDEX IF NOT EXISTS idx_audit_time   ON audit_log(created_at DESC);

-- ═══════════════════════════════════════════════════════════
--  ТРИГГЕРЫ: авто-статус товара
-- ═══════════════════════════════════════════════════════════
CREATE OR REPLACE FUNCTION check_product_stock() RETURNS TRIGGER AS $$
BEGIN
    IF (SELECT COUNT(*) FROM items
        WHERE product_id = NEW.product_id AND is_sold = FALSE) = 0
       AND (SELECT needs_data FROM products WHERE id = NEW.product_id) = FALSE
    THEN
        UPDATE products SET status = 'draft' WHERE id = NEW.product_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_auto_draft ON items;
CREATE TRIGGER trg_auto_draft
AFTER UPDATE OF is_sold ON items
FOR EACH ROW WHEN (NEW.is_sold = TRUE)
EXECUTE FUNCTION check_product_stock();

CREATE OR REPLACE FUNCTION activate_product() RETURNS TRIGGER AS $$
BEGIN
    UPDATE products SET status = 'active' WHERE id = NEW.product_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_auto_active ON items;
CREATE TRIGGER trg_auto_active
AFTER INSERT ON items
FOR EACH ROW
EXECUTE FUNCTION activate_product();
"""

# Убираем служебный маркер
SCHEMA = SCHEMA.replace("PRAGMA_COMPAT:\n", "")


async def run_migrations(pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(SCHEMA)
