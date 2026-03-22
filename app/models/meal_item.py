from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.meal import Meal
    from app.models.product import Product


class MealItem(Base):
    __tablename__ = "meal_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    meal_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("meals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    weight_grams: Mapped[float] = mapped_column(Float, nullable=False)
    calculated_kcal: Mapped[float] = mapped_column(Float, nullable=False)

    meal: Mapped["Meal"] = relationship(back_populates="items")
    product: Mapped["Product"] = relationship(back_populates="meal_items")
