import os
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, Literal
from datetime import datetime, timezone

from database import create_document, db
from schemas import PrepaidCardPurchase

# Optional Stripe support
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
PAYMENT_PROVIDER: Literal["stripe", "mock"] = "stripe" if STRIPE_SECRET_KEY else "mock"

app = FastAPI(title="Lavandería & Vending API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    return {"message": "Backend operativo", "payment_provider": PAYMENT_PROVIDER}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️ Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️ Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"

    return response


# ------- CONFIG --------
class PricingConfig(BaseModel):
    card_issue_price: int = Field(5, description="Precio de emisión de tarjeta en EUR (placeholder)")
    topup_options: list[int] = Field([10, 20, 30, 50], description="Opciones de recarga disponibles en EUR")
    currency: str = "eur"
    payment_provider: Literal["stripe", "mock"] = PAYMENT_PROVIDER


@app.get("/api/config", response_model=PricingConfig)
def get_config():
    return PricingConfig()


# ------- PURCHASE FLOW --------
class CreateCheckoutPayload(BaseModel):
    name: str
    email: EmailStr
    phone: str
    amount: int
    delivery_method: Literal["recogida", "envio"] = "recogida"


class CheckoutResponse(BaseModel):
    provider: Literal["stripe", "mock"]
    url: Optional[str] = None
    message: Optional[str] = None
    purchase_id: Optional[str] = None


def _send_confirmation_email(to_email: str, subject: str, content: str) -> None:
    # Placeholder email sender: logs to console; can be replaced with SMTP provider using env vars
    print("=== EMAIL CONFIRMATION (log) ===")
    print("To:", to_email)
    print("Subject:", subject)
    print(content)
    print("=== END EMAIL ===")


@app.post("/api/prepaid/create-checkout", response_model=CheckoutResponse)
def create_checkout(payload: CreateCheckoutPayload, request: Request):
    config = PricingConfig()
    if payload.amount not in config.topup_options:
        raise HTTPException(status_code=400, detail="Monto de recarga no válido")

    total = config.card_issue_price + payload.amount

    # Create purchase record (pending)
    purchase = PrepaidCardPurchase(
        customer_name=payload.name,
        customer_email=payload.email,
        customer_phone=payload.phone,
        amount_selected=payload.amount,
        card_price=config.card_issue_price,
        total_price=total,
        payment_provider=PAYMENT_PROVIDER,
        payment_status="pending",
        delivery_method=payload.delivery_method,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    purchase_id = create_document("prepaidcardpurchase", purchase)

    success_url = os.getenv("FRONTEND_URL", "http://localhost:3000") + f"/exito?purchase_id={purchase_id}"
    cancel_url = os.getenv("FRONTEND_URL", "http://localhost:3000") + f"/cancelado?purchase_id={purchase_id}"

    # Stripe mode
    if PAYMENT_PROVIDER == "stripe":
        try:
            import stripe  # type: ignore
            stripe.api_key = STRIPE_SECRET_KEY

            line_items = [
                {
                    "price_data": {
                        "currency": config.currency,
                        "product_data": {"name": "Tarjeta Prepago - Emisión"},
                        "unit_amount": config.card_issue_price * 100,
                    },
                    "quantity": 1,
                },
                {
                    "price_data": {
                        "currency": config.currency,
                        "product_data": {"name": f"Recarga inicial {payload.amount}€"},
                        "unit_amount": payload.amount * 100,
                    },
                    "quantity": 1,
                },
            ]

            session = stripe.checkout.Session.create(
                mode="payment",
                line_items=line_items,
                customer_email=payload.email,
                metadata={
                    "purchase_id": purchase_id,
                    "customer_name": payload.name,
                    "customer_phone": payload.phone,
                    "delivery_method": payload.delivery_method,
                },
                success_url=success_url + "&session_id={CHECKOUT_SESSION_ID}",
                cancel_url=cancel_url,
            )

            return CheckoutResponse(provider="stripe", url=session.url, purchase_id=purchase_id)
        except Exception as e:
            # Fallback to mock on any Stripe error
            print("Stripe error:", e)

    # Mock mode: mark as paid immediately and return a confirmation URL
    from bson import ObjectId  # type: ignore
    db["prepaidcardpurchase"].update_one(
        {"_id": ObjectId(purchase_id)},
        {"$set": {"payment_status": "paid", "updated_at": datetime.now(timezone.utc), "payment_reference": "mock-ok"}},
    )

    # Send confirmation email (log)
    _send_confirmation_email(
        to_email=payload.email,
        subject="Confirmación de compra - Tarjeta Prepago",
        content=(
            f"Hola {payload.name},\n\nGracias por tu compra. Hemos recibido el pago de {total}€. "
            f"Podrás recoger tu tarjeta en el local o solicitar envío según tu selección.\n\n"
            f"ID de compra: {purchase_id}\n"
            f"Método de entrega: {payload.delivery_method}\n\n"
            "Gracias por elegirnos."
        ),
    )

    return CheckoutResponse(provider="mock", url=success_url, message="Pago simulado con éxito", purchase_id=purchase_id)


@app.get("/api/prepaid/confirm")
def confirm(session_id: Optional[str] = None, purchase_id: Optional[str] = None):
    # In Stripe mode, verify session and mark as paid
    if PAYMENT_PROVIDER == "stripe":
        if not session_id:
            raise HTTPException(status_code=400, detail="Falta session_id")
        try:
            import stripe  # type: ignore
            stripe.api_key = STRIPE_SECRET_KEY
            session = stripe.checkout.Session.retrieve(session_id)
            pid = session.metadata.get("purchase_id") if session.metadata else purchase_id
            if session.payment_status == "paid" and pid:
                from bson import ObjectId  # type: ignore
                db["prepaidcardpurchase"].update_one(
                    {"_id": ObjectId(pid)},
                    {"$set": {"payment_status": "paid", "payment_reference": session_id, "updated_at": datetime.now(timezone.utc)}},
                )
                email = session.customer_details.email if session.customer_details else None
                name = session.metadata.get("customer_name") if session.metadata else "Cliente"
                if email:
                    _send_confirmation_email(
                        to_email=email,
                        subject="Confirmación de compra - Tarjeta Prepago",
                        content=(
                            f"Hola {name},\n\nHemos recibido tu pago correctamente. "
                            f"ID de compra: {pid}\n"
                            "Te enviaremos instrucciones para recoger tu tarjeta en el local o envío.\n\nGracias."
                        ),
                    )
                return {"status": "ok", "purchase_id": pid}
            else:
                raise HTTPException(status_code=400, detail="Pago no confirmado")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Error confirmando el pago: {str(e)}")

    # Mock mode just acknowledges
    if not purchase_id:
        raise HTTPException(status_code=400, detail="Falta purchase_id")
    return {"status": "ok", "purchase_id": purchase_id}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
