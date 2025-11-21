"""
Database Schemas

Define your MongoDB collection schemas here using Pydantic models.
These schemas are used for data validation in your application.

Each Pydantic model represents a collection in your database.
Model name is converted to lowercase for the collection name:
- User -> "user" collection
- Product -> "product" collection
- BlogPost -> "blogs" collection
"""

from pydantic import BaseModel, Field, EmailStr
from typing import Optional, Literal
from datetime import datetime

# --- Business-specific schemas ---

class Customer(BaseModel):
    """
    Customers who purchase or use services
    Collection name: "customer"
    """
    name: str = Field(..., description="Nombre completo del cliente")
    email: EmailStr = Field(..., description="Email del cliente")
    phone: str = Field(..., description="Teléfono del cliente")

class PrepaidCardPurchase(BaseModel):
    """
    Registro de compras de tarjeta prepago
    Collection name: "prepaidcardpurchase"
    """
    customer_name: str = Field(..., description="Nombre del cliente")
    customer_email: EmailStr = Field(..., description="Email del cliente")
    customer_phone: str = Field(..., description="Teléfono del cliente")
    amount_selected: int = Field(..., ge=0, description="Monto de recarga seleccionado en EUR")
    card_price: int = Field(..., ge=0, description="Precio de emisión de la tarjeta en EUR")
    total_price: int = Field(..., ge=0, description="Total a pagar en EUR")
    payment_provider: Literal["stripe", "mock"] = Field(..., description="Proveedor de pago usado")
    payment_status: Literal["pending", "paid", "failed"] = Field("pending", description="Estado del pago")
    payment_reference: Optional[str] = Field(None, description="ID de pago o referencia del proveedor")
    delivery_method: Literal["recogida", "envio"] = Field("recogida", description="Cómo recibirá la tarjeta física")
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

# Example (kept for reference, not used directly)
class User(BaseModel):
    name: str
    email: str
    address: str
    age: Optional[int] = None
    is_active: bool = True

class Product(BaseModel):
    title: str
    description: Optional[str] = None
    price: float
    category: str
    in_stock: bool = True
