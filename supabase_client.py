import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from supabase import AsyncClient

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

ENV_PATH = Path(__file__).resolve().parent / ".env"

DEFAULT_PRODUCTS = [
    {
        "id": 1,
        "name": "Camiseta urbana",
        "description": "Camiseta de algodón con corte moderno y estampado minimalista.",
        "price": 22.0,
        "stock": 15,
        "category": "Camisetas",
        "image_url": "https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?auto=format&fit=crop&w=500&q=60",
    },
    {
        "id": 2,
        "name": "Pantalón chino",
        "description": "Pantalón versátil para oficina o fin de semana.",
        "price": 34.0,
        "stock": 10,
        "category": "Pantalones",
        "image_url": "https://images.unsplash.com/photo-1512436991641-6745cdb1723f?auto=format&fit=crop&w=500&q=60",
    },
    {
        "id": 3,
        "name": "Sudadera con capucha",
        "description": "Sudadera cómoda y cálida para el día a día.",
        "price": 39.0,
        "stock": 8,
        "category": "Sudaderas",
        "image_url": "https://images.unsplash.com/photo-1512436991641-6745cdb1723f?auto=format&fit=crop&w=500&q=60",
    },
    {
        "id": 4,
        "name": "Chaqueta ligera",
        "description": "Chaqueta urbana para clima fresco con diseño casual.",
        "price": 59.0,
        "stock": 5,
        "category": "Chaquetas",
        "image_url": "https://images.unsplash.com/photo-1521334884684-d80222895322?auto=format&fit=crop&w=500&q=60",
    },
    {
        "id": 5,
        "name": "Vestido de día",
        "description": "Vestido fresco y elegante para un look informal.",
        "price": 48.0,
        "stock": 6,
        "category": "Vestidos",
        "image_url": "https://images.unsplash.com/photo-1483985988355-763728e1935b?auto=format&fit=crop&w=500&q=60",
    },
]


class SupabaseStoreError(Exception):
    pass


def _load_env() -> Dict[str, str]:
    env: Dict[str, str] = dict(os.environ)
    if not ENV_PATH.exists():
        return env

    for raw_line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")

    return env


def _get_supabase_config() -> Dict[str, str]:
    env = _load_env()
    url = env.get("SUPABASE_URL")
    key = env.get("SUPABASE_KEY")

    if not url or not key:
        raise SupabaseStoreError(
            "Missing SUPABASE_URL or SUPABASE_KEY in environment or backend/.env"
        )

    return {"url": url, "key": key}


async def get_supabase_client() -> AsyncClient:
    cfg = _get_supabase_config()
    return AsyncClient(cfg["url"], cfg["key"])


async def _ensure_success(response: Any) -> Any:
    if getattr(response, "error", None):
        raise SupabaseStoreError(response.error)
    return response.data


async def list_products() -> List[Dict[str, Any]]:
    client = await get_supabase_client()
    response = await client.table("products").select("*").order("id").execute()
    return await _ensure_success(response)


async def get_product(product_id: int) -> Optional[Dict[str, Any]]:
    client = await get_supabase_client()
    response = await (
        client.table("products").select("*").eq("id", product_id).limit(1).execute()
    )
    data = await _ensure_success(response)
    return data[0] if data else None


async def list_sales() -> List[Dict[str, Any]]:
    client = await get_supabase_client()
    response = await client.table("sales").select("*").order("created_at", desc=True).execute()
    return await _ensure_success(response)


async def get_sales_summary() -> Dict[str, Any]:
    sales = await list_sales()
    return {
        "total_orders": len(sales),
        "total_revenue": sum(float(sale.get("total", 0)) for sale in sales),
        "total_items_sold": sum(int(sale.get("item_count", 0)) for sale in sales),
    }


async def create_product(product: Dict[str, Any]) -> Dict[str, Any]:
    client = await get_supabase_client()
    response = await client.table("products").insert(product).select("*").execute()
    data = await _ensure_success(response)
    return data[0]


async def update_product_stock(product_id: int, new_stock: int) -> Dict[str, Any]:
    client = await get_supabase_client()
    response = await (
        client.table("products")
        .update({"stock": new_stock})
        .eq("id", product_id)
        .select("*")
        .execute()
    )
    data = await _ensure_success(response)
    return data[0]


async def create_sale(
    items: List[Dict[str, Any]], customer: str = "Cliente demo"
) -> Dict[str, Any]:
    try:
        logger.info(f"[CHECKOUT] Iniciando checkout con {len(items)} items para cliente: {customer}")
        
        if not items:
            raise SupabaseStoreError("El carrito debe contener al menos un item.")

        product_ids = [item["product_id"] for item in items]
        logger.info(f"[CHECKOUT] Product IDs solicitados: {product_ids}")
        
        client = await get_supabase_client()
        logger.info("[CHECKOUT] Cliente Supabase obtenido")
        
        stock_response = await (
            client.table("products")
            .select("*")
            .in_("id", product_ids)
            .execute()
        )
        logger.info(f"[CHECKOUT] Respuesta de inventario: {stock_response}")
        
        inventory = {product["id"]: product for product in await _ensure_success(stock_response)}
        logger.info(f"[CHECKOUT] Inventario procesado: {list(inventory.keys())}")

        line_items = []
        total = 0.0
        item_count = 0

        for item in items:
            logger.info(f"[CHECKOUT] Procesando item: {item}")
            product = inventory.get(item["product_id"])
            if not product:
                raise SupabaseStoreError(f"Producto {item['product_id']} no encontrado.")
            if item["quantity"] > int(product["stock"]):
                raise SupabaseStoreError(
                    f"No hay suficiente stock para {product['name']}. Disponible: {product['stock']}"
                )

            amount = float(product["price"]) * item["quantity"]
            line_items.append(
                {
                    "product_id": product["id"],
                    "quantity": item["quantity"],
                    "unit_price": float(product["price"]),
                    "total": round(amount, 2),
                }
            )
            total += amount
            item_count += item["quantity"]
            logger.info(f"[CHECKOUT] Item agregado: {product['name']} x{item['quantity']}")

        logger.info(f"[CHECKOUT] Insertando venta con total: {total}, items: {item_count}")
        sale_response = await client.table("sales").insert(
            {
                "customer": customer,
                "total": round(total, 2),
                "item_count": item_count,
            }
        ).select("id, created_at, customer, total, item_count").execute()
        
        logger.info(f"[CHECKOUT] Respuesta de venta: {sale_response}")
        sale_record = await _ensure_success(sale_response)
        sale_id = sale_record[0]["id"]
        logger.info(f"[CHECKOUT] Venta creada con ID: {sale_id}")

        logger.info(f"[CHECKOUT] Insertando {len(line_items)} items de venta")
        items_response = await client.table("sale_items").insert(
            [
                {
                    "sale_id": sale_id,
                    "product_id": line_item["product_id"],
                    "quantity": line_item["quantity"],
                    "unit_price": line_item["unit_price"],
                    "total": line_item["total"],
                }
                for line_item in line_items
            ]
        ).execute()
        
        logger.info(f"[CHECKOUT] Respuesta de items: {items_response}")
        await _ensure_success(items_response)
        logger.info("[CHECKOUT] Items de venta insertados")

        logger.info(f"[CHECKOUT] Actualizando stock de {len(items)} productos")
        for item in items:
            product = inventory[item["product_id"]]
            new_stock = int(product["stock"]) - item["quantity"]
            logger.info(f"[CHECKOUT] Actualizando producto {item['product_id']}: stock {product['stock']} -> {new_stock}")
            await client.table("products").update(
                {"stock": new_stock}
            ).eq("id", item["product_id"]).execute()

        logger.info("[CHECKOUT] Checkout completado exitosamente")
        return {
            "sale": sale_record[0],
            "items": line_items,
        }
    except Exception as e:
        logger.error(f"[CHECKOUT] Error: {type(e).__name__}: {str(e)}", exc_info=True)
        raise


async def reset_store(initial_products: Optional[List[Dict[str, Any]]] = None) -> None:
    client = await get_supabase_client()
    await client.table("sale_items").delete().neq("id", 0).execute()
    await client.table("sales").delete().neq("id", 0).execute()
    await client.table("products").delete().neq("id", 0).execute()

    products = initial_products if initial_products is not None else DEFAULT_PRODUCTS
    await client.table("products").insert(products).execute()


async def get_sale_items(sale_id: int) -> List[Dict[str, Any]]:
    client = await get_supabase_client()
    response = await (
        client.table("sale_items").select("*").eq("sale_id", sale_id).execute()
    )
    return await _ensure_success(response)
