import hashlib
import aiohttp
from config import (
    CRYPTOBOT_TOKEN, CRYPTOBOT_API, CRYPTOBOT_DIVISOR,
    FREEKASSA_SHOP_ID, FREEKASSA_SECRET1, FREEKASSA_SECRET2,
    FREEKASSA_CURRENCY, STARS_RATE,
)


async def cryptobot_create_invoice(amount_usd: float, description: str) -> dict | None:
    charge = round(amount_usd / CRYPTOBOT_DIVISOR, 2)
    async with aiohttp.ClientSession() as s:
        headers = {"Crypto-Pay-API-Token": CRYPTOBOT_TOKEN}
        async with s.post(f"{CRYPTOBOT_API}/createInvoice", json={
            "asset": "USDT", "amount": str(charge),
            "description": description, "expires_in": 3600,
        }, headers=headers) as r:
            data = await r.json()
            if data.get("ok"):
                inv = data["result"]
                inv["_credited"] = amount_usd
                return inv
            return None


async def cryptobot_get_invoice(invoice_id: int) -> dict | None:
    async with aiohttp.ClientSession() as s:
        headers = {"Crypto-Pay-API-Token": CRYPTOBOT_TOKEN}
        async with s.get(f"{CRYPTOBOT_API}/getInvoices",
                         params={"invoice_ids": invoice_id},
                         headers=headers) as r:
            data = await r.json()
            if data.get("ok") and data["result"]["items"]:
                return data["result"]["items"][0]
            return None


def freekassa_generate_url(order_id: str, amount_rub: float) -> str:
    sign = hashlib.md5(
        f"{FREEKASSA_SHOP_ID}:{amount_rub:.2f}:{FREEKASSA_SECRET1}:{FREEKASSA_CURRENCY}:{order_id}".encode()
    ).hexdigest()
    return (f"https://pay.fk.money/?m={FREEKASSA_SHOP_ID}&oa={amount_rub:.2f}"
            f"&currency={FREEKASSA_CURRENCY}&o={order_id}&s={sign}&lang=ru")


def freekassa_verify_webhook(params: dict) -> bool:
    sign = hashlib.md5(
        f"{FREEKASSA_SHOP_ID}:{params.get('AMOUNT','')}:{FREEKASSA_SECRET2}:{params.get('MERCHANT_ORDER_ID','')}".encode()
    ).hexdigest()
    return sign == params.get("SIGN", "")


def stars_to_usd(stars: int) -> float:
    return round(stars * STARS_RATE, 4)


def usd_to_stars(amount_usd: float) -> int:
    return max(1, int(amount_usd / STARS_RATE))
