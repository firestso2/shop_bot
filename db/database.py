"""
Весь слой работы с БД (PostgreSQL / asyncpg).
"""
import json
import random
import string
from datetime import datetime, timedelta, timezone

from db.pool import get_pool


# ════════════════════════════════════════════════════════════════════════════
#  УТИЛИТЫ
# ════════════════════════════════════════════════════════════════════════════

def gen_order_code(length: int = 12) -> str:
    chars = string.ascii_uppercase + string.digits
    raw = ''.join(random.choices(chars, k=length))
    return '-'.join(raw[i:i+4] for i in range(0, len(raw), 4))


async def log_action(user_id: int | None, action: str, details: dict | None = None):
    pool = get_pool()
    await pool.execute(
        "INSERT INTO audit_log(user_id, action, details) VALUES($1,$2,$3)",
        user_id, action,
        json.dumps(details, default=str) if details else None
    )


# ════════════════════════════════════════════════════════════════════════════
#  USERS
# ════════════════════════════════════════════════════════════════════════════

async def get_user(user_id: int) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow("SELECT * FROM users WHERE id=$1", user_id)
    return dict(row) if row else None


async def ensure_user(user_id: int, username: str) -> None:
    pool = get_pool()
    await pool.execute(
        "INSERT INTO users(id,username) VALUES($1,$2) "
        "ON CONFLICT(id) DO UPDATE SET username=EXCLUDED.username",
        user_id, username or ""
    )


async def set_subscribed(user_id: int, referrer_id: int | None) -> None:
    pool = get_pool()
    user = await pool.fetchrow("SELECT referrer_id FROM users WHERE id=$1", user_id)
    current_ref = user["referrer_id"] if user else None

    if referrer_id and current_ref is None and referrer_id != user_id:
        ref_ok = await pool.fetchval("SELECT id FROM users WHERE id=$1", referrer_id)
        if ref_ok:
            await pool.execute(
                "UPDATE users SET is_subscribed=TRUE, referrer_id=$1 WHERE id=$2",
                referrer_id, user_id
            )
            await log_action(user_id, "subscribed", {"referrer": referrer_id})
            return

    await pool.execute("UPDATE users SET is_subscribed=TRUE WHERE id=$1", user_id)
    await log_action(user_id, "subscribed")


async def add_balance(user_id: int, amount: float) -> float:
    pool = get_pool()
    row = await pool.fetchrow(
        "UPDATE users SET balance=balance+$1 WHERE id=$2 RETURNING balance",
        amount, user_id
    )
    return float(row["balance"]) if row else 0.0


async def get_referrer_id(user_id: int) -> int | None:
    pool = get_pool()
    return await pool.fetchval("SELECT referrer_id FROM users WHERE id=$1", user_id)


async def add_ref_earned(referrer_id: int, bonus: float) -> None:
    pool = get_pool()
    await pool.execute(
        "UPDATE users SET balance=balance+$1, ref_earned=ref_earned+$1 WHERE id=$2",
        bonus, referrer_id
    )


async def get_all_user_ids() -> list[int]:
    pool = get_pool()
    rows = await pool.fetch("SELECT id FROM users")
    return [r["id"] for r in rows]


async def admin_set_balance(user_id: int, delta: float) -> float | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "UPDATE users SET balance=balance+$1 WHERE id=$2 RETURNING balance",
        delta, user_id
    )
    return float(row["balance"]) if row else None


async def get_users_with_balance_above(threshold: float) -> list[int]:
    pool = get_pool()
    rows = await pool.fetch("SELECT id FROM users WHERE balance>=$1", threshold)
    return [r["id"] for r in rows]


async def get_users_bought_product(product_id: int,
                                   since_days: int | None = None) -> list[int]:
    pool = get_pool()
    if since_days:
        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=since_days)
        rows = await pool.fetch(
            "SELECT DISTINCT user_id FROM orders "
            "WHERE product_id=$1 AND status='completed' AND created_at>=$2",
            product_id, cutoff
        )
    else:
        rows = await pool.fetch(
            "SELECT DISTINCT user_id FROM orders WHERE product_id=$1 AND status='completed'",
            product_id
        )
    return [r["user_id"] for r in rows]


async def get_stats() -> dict:
    pool = get_pool()
    ut  = await pool.fetchval("SELECT COUNT(*) FROM users")
    ud  = await pool.fetchval(
        "SELECT COUNT(*) FROM users WHERE DATE(joined_at)=CURRENT_DATE"
    )
    rev = await pool.fetchval(
        "SELECT COALESCE(SUM(credited),0) FROM payments WHERE status='paid'"
    )
    ref = await pool.fetchval("SELECT COALESCE(SUM(ref_earned),0) FROM users")
    ord_= await pool.fetchval("SELECT COUNT(*) FROM orders")
    top = await pool.fetchval(
        "SELECT COALESCE(SUM(credited),0) FROM payments "
        "WHERE status='paid' AND method='cryptobot'"
    )
    return {
        "users_total": ut, "users_today": ud,
        "revenue": float(rev), "ref_paid": float(ref),
        "orders_count": ord_, "crypto_topup": float(top)
    }


# ── CRM ──────────────────────────────────────────────────────────────────────

async def get_user_crm(user_id: int) -> dict | None:
    """Полный профиль пользователя для CRM-модуля."""
    pool = get_pool()
    user = await pool.fetchrow("SELECT * FROM users WHERE id=$1", user_id)
    if not user:
        return None

    orders = await pool.fetch(
        "SELECT order_code, total, status, created_at, "
        "(SELECT name FROM products WHERE id=o.product_id) AS product_name "
        "FROM orders o WHERE user_id=$1 ORDER BY created_at DESC",
        user_id
    )
    referrals = await pool.fetch(
        "SELECT id, username FROM users WHERE referrer_id=$1", user_id
    )
    return {
        "user": dict(user),
        "orders": [dict(r) for r in orders],
        "referrals": [dict(r) for r in referrals],
    }


async def get_top_referrers(limit: int = 10) -> list[dict]:
    """Топ рефералов по количеству приглашённых и заработку."""
    pool = get_pool()
    rows = await pool.fetch(
        """
        SELECT u.id, u.username, u.ref_earned,
               (SELECT COUNT(*) FROM users WHERE referrer_id=u.id) AS ref_count
        FROM users u
        WHERE u.ref_earned > 0
        ORDER BY ref_count DESC, u.ref_earned DESC
        LIMIT $1
        """,
        limit
    )
    return [dict(r) for r in rows]


# ════════════════════════════════════════════════════════════════════════════
#  PAYMENTS
# ════════════════════════════════════════════════════════════════════════════

async def create_payment(user_id: int, amount: float, credited: float,
                         method: str, external_id: str) -> int:
    pool = get_pool()
    return await pool.fetchval(
        "INSERT INTO payments(user_id,amount,credited,method,external_id) "
        "VALUES($1,$2,$3,$4,$5) RETURNING id",
        user_id, amount, credited, method, external_id
    )


async def mark_payment_paid(external_id: str) -> dict | None:
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT id,user_id,credited,status FROM payments "
                "WHERE external_id=$1 FOR UPDATE",
                external_id
            )
            if not row or row["status"] == "paid":
                return None
            await conn.execute(
                "UPDATE payments SET status='paid' WHERE external_id=$1", external_id
            )
    return {"user_id": row["user_id"], "credited": float(row["credited"])}


async def get_pending_cryptobot_payments() -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT id,user_id,credited,external_id FROM payments "
        "WHERE status='pending' AND method='cryptobot' "
        "AND created_at > NOW() - INTERVAL '2 hours'"
    )
    return [dict(r) for r in rows]


# ════════════════════════════════════════════════════════════════════════════
#  CATEGORIES
# ════════════════════════════════════════════════════════════════════════════

async def get_root_categories() -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT * FROM categories WHERE parent_id IS NULL ORDER BY name"
    )
    return [dict(r) for r in rows]


async def get_child_categories(parent_id: int) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT * FROM categories WHERE parent_id=$1 ORDER BY name", parent_id
    )
    return [dict(r) for r in rows]


async def get_category(cat_id: int) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow("SELECT * FROM categories WHERE id=$1", cat_id)
    return dict(row) if row else None


async def create_category(name: str, parent_id: int | None) -> int:
    pool = get_pool()
    return await pool.fetchval(
        "INSERT INTO categories(name,parent_id) VALUES($1,$2) RETURNING id",
        name, parent_id
    )


async def delete_category(cat_id: int) -> bool:
    pool = get_pool()
    ch = await pool.fetchval(
        "SELECT COUNT(*) FROM categories WHERE parent_id=$1", cat_id
    )
    pr = await pool.fetchval(
        "SELECT COUNT(*) FROM products WHERE category_id=$1", cat_id
    )
    if ch > 0 or pr > 0:
        return False
    await pool.execute("DELETE FROM categories WHERE id=$1", cat_id)
    return True


async def get_all_categories_flat() -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT * FROM categories ORDER BY parent_id NULLS FIRST, name"
    )
    return [dict(r) for r in rows]


async def get_all_categories_with_products() -> tuple[list[dict], list[dict]]:
    pool = get_pool()
    cats = await pool.fetch("SELECT * FROM categories ORDER BY name")
    prods = await pool.fetch(
        """SELECT p.id, p.name, p.price, p.category_id, p.needs_data,
           (SELECT COUNT(DISTINCT item_group) FROM items
            WHERE product_id=p.id AND is_sold=FALSE) AS stock
           FROM products p WHERE p.status='active' ORDER BY p.name"""
    )
    return [dict(r) for r in cats], [dict(r) for r in prods]


# ════════════════════════════════════════════════════════════════════════════
#  PRODUCTS
# ════════════════════════════════════════════════════════════════════════════

async def get_active_products(cat_id: int,
                              limit: int = 10, offset: int = 0) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        """SELECT p.*,
           (SELECT COUNT(DISTINCT item_group) FROM items
            WHERE product_id=p.id AND is_sold=FALSE) AS stock
           FROM products p
           WHERE p.category_id=$1 AND p.status='active'
           ORDER BY p.name LIMIT $2 OFFSET $3""",
        cat_id, limit, offset
    )
    return [dict(r) for r in rows]


async def count_active_products(cat_id: int) -> int:
    pool = get_pool()
    return await pool.fetchval(
        "SELECT COUNT(*) FROM products WHERE category_id=$1 AND status='active'",
        cat_id
    )


async def get_draft_products() -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        """SELECT p.*, c.name AS cat_name,
           (SELECT COUNT(DISTINCT item_group) FROM items
            WHERE product_id=p.id AND is_sold=FALSE) AS stock
           FROM products p JOIN categories c ON c.id=p.category_id
           WHERE p.status='draft' ORDER BY p.name"""
    )
    return [dict(r) for r in rows]


async def get_all_products() -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        """SELECT p.*, c.name AS cat_name,
           (SELECT COUNT(DISTINCT item_group) FROM items
            WHERE product_id=p.id AND is_sold=FALSE) AS stock
           FROM products p JOIN categories c ON c.id=p.category_id
           ORDER BY p.status DESC, p.name"""
    )
    return [dict(r) for r in rows]


async def get_product(product_id: int) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        """SELECT p.*,
           (SELECT COUNT(DISTINCT item_group) FROM items
            WHERE product_id=p.id AND is_sold=FALSE) AS stock
           FROM products p WHERE p.id=$1""",
        product_id
    )
    return dict(row) if row else None


async def create_product(cat_id: int, name: str, description: str | None,
                         price: float, needs_data: bool = False,
                         data_request_text: str | None = None,
                         bulk_min_qty: int = 3,
                         bulk_discount_pct: float = 5.0) -> int:
    pool = get_pool()
    status = 'active' if needs_data else 'draft'
    return await pool.fetchval(
        """INSERT INTO products
           (category_id,name,description,price,needs_data,data_request_text,
            status,bulk_min_qty,bulk_discount_pct)
           VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9) RETURNING id""",
        cat_id, name, description, price, needs_data,
        data_request_text, status, bulk_min_qty, bulk_discount_pct
    )


async def update_product_instruction(product_id: int,
                                     text: str | None = None,
                                     file_id: str | None = None) -> None:
    pool = get_pool()
    if text is not None:
        await pool.execute(
            "UPDATE products SET instruction_text=$1 WHERE id=$2", text, product_id
        )
    if file_id is not None:
        await pool.execute(
            "UPDATE products SET instruction_file=$1 WHERE id=$2", file_id, product_id
        )


async def update_product_data_request(product_id: int, text: str) -> None:
    pool = get_pool()
    await pool.execute(
        "UPDATE products SET data_request_text=$1 WHERE id=$2", text, product_id
    )


async def update_product_price(product_id: int, price: float) -> None:
    pool = get_pool()
    await pool.execute("UPDATE products SET price=$1 WHERE id=$2", price, product_id)


async def delete_product(product_id: int) -> None:
    pool = get_pool()
    await pool.execute("DELETE FROM products WHERE id=$1", product_id)


async def get_low_stock_products(threshold: int) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        """SELECT p.id, p.name,
           (SELECT COUNT(DISTINCT item_group) FROM items
            WHERE product_id=p.id AND is_sold=FALSE) AS stock
           FROM products p
           WHERE p.status='active' AND p.needs_data=FALSE
           HAVING (SELECT COUNT(DISTINCT item_group) FROM items
                   WHERE product_id=p.id AND is_sold=FALSE) <= $1
           GROUP BY p.id, p.name""",
        threshold
    )
    return [dict(r) for r in rows]


# ════════════════════════════════════════════════════════════════════════════
#  ITEMS
# ════════════════════════════════════════════════════════════════════════════

async def get_next_item_group(product_id: int) -> int:
    pool = get_pool()
    val = await pool.fetchval(
        "SELECT COALESCE(MAX(item_group),0)+1 FROM items WHERE product_id=$1",
        product_id
    )
    return val or 1


async def add_items(product_id: int, contents: list[str], item_type: str) -> int:
    pool = get_pool()
    max_group = await pool.fetchval(
        "SELECT COALESCE(MAX(item_group),0) FROM items WHERE product_id=$1",
        product_id
    )
    start = (max_group or 0) + 1
    await pool.executemany(
        "INSERT INTO items(product_id,content,type,item_group) VALUES($1,$2,$3,$4)",
        [(product_id, c, item_type, start + i) for i, c in enumerate(contents)]
    )
    return len(contents)


async def add_file_to_group(product_id: int, file_id: str, group: int) -> None:
    pool = get_pool()
    await pool.execute(
        "INSERT INTO items(product_id,content,type,item_group) VALUES($1,$2,'file',$3)",
        product_id, file_id, group
    )


async def pop_items(product_id: int, qty: int) -> list[list[dict]] | None:
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            group_rows = await conn.fetch(
                "SELECT DISTINCT item_group FROM items "
                "WHERE product_id=$1 AND is_sold=FALSE ORDER BY item_group LIMIT $2",
                product_id, qty
            )
            if len(group_rows) < qty:
                return None
            groups = [r["item_group"] for r in group_rows]
            await conn.execute(
                "UPDATE items SET is_sold=TRUE "
                "WHERE product_id=$1 AND item_group=ANY($2::int[])",
                product_id, groups
            )
            all_items = await conn.fetch(
                "SELECT * FROM items WHERE product_id=$1 AND item_group=ANY($2::int[]) "
                "ORDER BY item_group, id",
                product_id, groups
            )
    result: dict[int, list] = {}
    for row in all_items:
        g = row["item_group"]
        result.setdefault(g, []).append(dict(row))
    return [result[g] for g in groups]


async def get_stock_count(product_id: int) -> int:
    pool = get_pool()
    val = await pool.fetchval(
        "SELECT COUNT(DISTINCT item_group) FROM items "
        "WHERE product_id=$1 AND is_sold=FALSE",
        product_id
    )
    return val or 0


# ════════════════════════════════════════════════════════════════════════════
#  COUPONS
# ════════════════════════════════════════════════════════════════════════════

async def get_coupon(code: str) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow("SELECT * FROM coupons WHERE code=$1", code)
    return dict(row) if row else None


async def coupon_use_count(code: str) -> int:
    pool = get_pool()
    return await pool.fetchval(
        "SELECT COUNT(*) FROM coupon_uses WHERE coupon_code=$1", code
    )


async def user_used_coupon(code: str, user_id: int) -> bool:
    pool = get_pool()
    return bool(await pool.fetchval(
        "SELECT 1 FROM coupon_uses WHERE coupon_code=$1 AND user_id=$2",
        code, user_id
    ))


async def record_coupon_use(code: str, user_id: int) -> None:
    pool = get_pool()
    await pool.execute(
        "INSERT INTO coupon_uses(coupon_code,user_id) VALUES($1,$2) ON CONFLICT DO NOTHING",
        code, user_id
    )


async def create_coupon(code: str, type_: str, value: float,
                        max_uses: int = 0, expire_days: int = 0) -> None:
    pool = get_pool()
    expire_at = (
        datetime.now(tz=timezone.utc) + timedelta(days=expire_days)
        if expire_days > 0 else None
    )
    await pool.execute(
        "INSERT INTO coupons(code,type,value,max_uses,expire_at) VALUES($1,$2,$3,$4,$5)",
        code, type_, value, max_uses, expire_at
    )


async def delete_coupon(code: str) -> None:
    pool = get_pool()
    await pool.execute("DELETE FROM coupons WHERE code=$1", code)


async def list_coupons() -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT c.*, (SELECT COUNT(*) FROM coupon_uses WHERE coupon_code=c.code) AS uses "
        "FROM coupons c ORDER BY created_at DESC"
    )
    return [dict(r) for r in rows]


def apply_discount(price: float, qty: int, coupon: dict | None,
                   bulk_min: int, bulk_pct: float) -> tuple[float, float, str]:
    """
    Скидки НЕ суммируются. Применяется большая.
    Возвращает (total, disc_pct_applied, description).
    """
    base = price * qty
    bulk_d = bulk_pct if qty >= bulk_min else 0.0

    coupon_d = 0.0
    if coupon:
        if coupon["type"] == "percent":
            coupon_d = float(coupon["value"])
        else:
            coupon_d = min(float(coupon["value"]) / base * 100, 100.0)

    if coupon_d >= bulk_d and coupon_d > 0:
        pct, desc = coupon_d, f"купон ({coupon['code']})"
    elif bulk_d > 0:
        pct, desc = bulk_d, f"опт (≥{bulk_min} шт.)"
    else:
        pct, desc = 0.0, ""

    total = round(base * (1 - pct / 100), 2)
    return total, pct, desc


# ════════════════════════════════════════════════════════════════════════════
#  ORDERS
# ════════════════════════════════════════════════════════════════════════════

async def create_order(user_id: int, product_id: int, qty: int, total: float,
                       status: str = "pending", discount_pct: float = 0,
                       coupon_code: str | None = None,
                       stars_charge_id: str | None = None) -> str:
    pool = get_pool()
    from config import ORDER_AUTO_CANCEL_HOURS
    deadline = datetime.now(tz=timezone.utc) + timedelta(hours=ORDER_AUTO_CANCEL_HOURS)

    async with pool.acquire() as conn:
        async with conn.transaction():
            while True:
                code = gen_order_code()
                exists = await conn.fetchval(
                    "SELECT id FROM orders WHERE order_code=$1", code
                )
                if not exists:
                    break
            await conn.execute(
                "UPDATE users SET balance=balance-$1 WHERE id=$2", total, user_id
            )
            await conn.execute(
                """INSERT INTO orders
                   (order_code,user_id,product_id,quantity,total,
                    discount_pct,coupon_code,status,stars_charge_id,deadline)
                   VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)""",
                code, user_id, product_id, qty, total,
                discount_pct, coupon_code, status,
                stars_charge_id, deadline
            )
    return code


async def create_order_no_deduct(user_id: int, product_id: int, qty: int,
                                  total: float, status: str = "pending",
                                  discount_pct: float = 0,
                                  coupon_code: str | None = None,
                                  stars_charge_id: str | None = None) -> str:
    """Создаёт заказ БЕЗ списания с баланса (для Stars — списание через Telegram)."""
    pool = get_pool()
    from config import ORDER_AUTO_CANCEL_HOURS
    deadline = datetime.now(tz=timezone.utc) + timedelta(hours=ORDER_AUTO_CANCEL_HOURS)

    async with pool.acquire() as conn:
        async with conn.transaction():
            while True:
                code = gen_order_code()
                exists = await conn.fetchval(
                    "SELECT id FROM orders WHERE order_code=$1", code
                )
                if not exists:
                    break
            await conn.execute(
                """INSERT INTO orders
                   (order_code,user_id,product_id,quantity,total,
                    discount_pct,coupon_code,status,stars_charge_id,deadline)
                   VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)""",
                code, user_id, product_id, qty, total,
                discount_pct, coupon_code, status,
                stars_charge_id, deadline
            )
    return code


async def update_order_status(code: str, status: str,
                              user_data: str | None = None,
                              assigned_admin: int | None = None) -> None:
    pool = get_pool()
    if user_data is not None and assigned_admin is not None:
        await pool.execute(
            "UPDATE orders SET status=$1, user_data=$2, assigned_admin=$3, taken_at=NOW() "
            "WHERE order_code=$4",
            status, user_data, assigned_admin, code
        )
    elif user_data is not None:
        await pool.execute(
            "UPDATE orders SET status=$1, user_data=$2 WHERE order_code=$3",
            status, user_data, code
        )
    elif assigned_admin is not None:
        await pool.execute(
            "UPDATE orders SET status=$1, assigned_admin=$2, taken_at=NOW() "
            "WHERE order_code=$3",
            status, assigned_admin, code
        )
    else:
        await pool.execute(
            "UPDATE orders SET status=$1 WHERE order_code=$2", status, code
        )


async def extend_order_deadline(code: str, hours: int) -> None:
    pool = get_pool()
    await pool.execute(
        "UPDATE orders SET deadline=deadline+($1 * INTERVAL '1 hour') WHERE order_code=$2",
        hours, code
    )


async def get_order_by_code(code: str) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        """SELECT o.*, p.name AS product_name, p.needs_data, p.data_request_text,
           u.username
           FROM orders o
           JOIN products p ON p.id=o.product_id
           JOIN users u ON u.id=o.user_id
           WHERE o.order_code=$1""",
        code
    )
    return dict(row) if row else None


async def get_user_orders(user_id: int, limit: int = 5,
                          offset: int = 0) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        """SELECT o.*, p.name AS product_name FROM orders o
           JOIN products p ON p.id=o.product_id
           WHERE o.user_id=$1 ORDER BY o.created_at DESC LIMIT $2 OFFSET $3""",
        user_id, limit, offset
    )
    return [dict(r) for r in rows]


async def get_orders_count(user_id: int) -> int:
    pool = get_pool()
    return await pool.fetchval(
        "SELECT COUNT(*) FROM orders WHERE user_id=$1", user_id
    )


async def get_pending_data_orders() -> list[dict]:
    """Заказы waiting_confirm — ждут, чтобы кто-то взял."""
    pool = get_pool()
    rows = await pool.fetch(
        """SELECT o.*, p.name AS product_name, u.username
           FROM orders o
           JOIN products p ON p.id=o.product_id
           JOIN users u ON u.id=o.user_id
           WHERE o.status='waiting_confirm'
           ORDER BY o.created_at"""
    )
    return [dict(r) for r in rows]


async def get_orders_past_deadline() -> list[dict]:
    """Заказы, у которых дедлайн истёк — для автовозврата."""
    pool = get_pool()
    rows = await pool.fetch(
        """SELECT * FROM orders
           WHERE status IN ('waiting_confirm','in_work')
           AND deadline < NOW()"""
    )
    return [dict(r) for r in rows]


async def get_in_work_order_for_user(user_id: int) -> dict | None:
    """Активный P2P заказ пользователя (если он в чате с админом)."""
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT * FROM orders WHERE user_id=$1 AND status='in_work'",
        user_id
    )
    return dict(row) if row else None


async def get_in_work_order_for_admin(admin_id: int) -> dict | None:
    """Заказ, который сейчас ведёт данный админ."""
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT o.*, p.name AS product_name, u.username "
        "FROM orders o "
        "JOIN products p ON p.id=o.product_id "
        "JOIN users u ON u.id=o.user_id "
        "WHERE o.assigned_admin=$1 AND o.status='in_work'",
        admin_id
    )
    return dict(row) if row else None


# ════════════════════════════════════════════════════════════════════════════
#  P2P MESSAGES
# ════════════════════════════════════════════════════════════════════════════

async def save_p2p_message(order_code: str, from_user: bool,
                           tg_msg_id: int, fwd_msg_id: int | None = None) -> None:
    pool = get_pool()
    await pool.execute(
        "INSERT INTO p2p_messages(order_code,from_user,tg_msg_id,fwd_msg_id) "
        "VALUES($1,$2,$3,$4)",
        order_code, from_user, tg_msg_id, fwd_msg_id
    )


# ════════════════════════════════════════════════════════════════════════════
#  STOCK NOTIFY
# ════════════════════════════════════════════════════════════════════════════

async def add_stock_notify(user_id: int, product_id: int) -> None:
    pool = get_pool()
    await pool.execute(
        "INSERT INTO stock_notify(user_id,product_id) VALUES($1,$2) ON CONFLICT DO NOTHING",
        user_id, product_id
    )


async def get_stock_notify_users(product_id: int) -> list[int]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT user_id FROM stock_notify WHERE product_id=$1", product_id
    )
    return [r["user_id"] for r in rows]


async def clear_stock_notify(product_id: int) -> None:
    pool = get_pool()
    await pool.execute("DELETE FROM stock_notify WHERE product_id=$1", product_id)


# ════════════════════════════════════════════════════════════════════════════
#  AUDIT LOG
# ════════════════════════════════════════════════════════════════════════════

async def get_audit_log(limit: int = 50, user_id: int | None = None) -> list[dict]:
    pool = get_pool()
    if user_id:
        rows = await pool.fetch(
            "SELECT * FROM audit_log WHERE user_id=$1 "
            "ORDER BY created_at DESC LIMIT $2",
            user_id, limit
        )
    else:
        rows = await pool.fetch(
            "SELECT * FROM audit_log ORDER BY created_at DESC LIMIT $1", limit
        )
    return [dict(r) for r in rows]
