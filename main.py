from typing import List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, conint

from supabase_client import (
    create_sale,
    get_sales_summary,
    get_supabase_client,
    list_products,
    list_sales,
    reset_store,
    SupabaseStoreError,
)

app = FastAPI(
    title="Tienda de ropa demo",
    description="Backend demo para una tienda de ropa con Supabase en persistencia real.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


class SaleItemIn(BaseModel):
    product_id: int
    quantity: conint(gt=0)


class CheckoutRequest(BaseModel):
    items: List[SaleItemIn]
    customer: str | None = "Cliente demo"

@app.get("/api/products")
async def get_products():
    try:
        products = await list_products()
        return products
    except SupabaseStoreError as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/sales")
async def get_sales():
    try:
        sales = await list_sales()
        summary = await get_sales_summary()
        return {"sales": sales, "summary": summary}
    except SupabaseStoreError as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/checkout")
async def checkout(order: CheckoutRequest):
    try:
        if not order.items:
            raise HTTPException(status_code=400, detail="El carrito está vacío.")

        items = [item.dict() for item in order.items]
        result = await create_sale(items, order.customer or "Cliente demo")

        return {
            "message": "Venta registrada con éxito.",
            "sale": result["sale"],
            "items": result["items"],
        }
    except SupabaseStoreError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/reset")
async def reset_endpoint():
    try:
        await reset_store()
        return {"message": "Datos de la tienda reiniciados."}
    except SupabaseStoreError as e:
        raise HTTPException(status_code=500, detail=str(e))
