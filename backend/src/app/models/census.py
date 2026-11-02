"""2021 Census demographic data."""

from __future__ import annotations

from sqlalchemy import Integer, SmallInteger, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CensusSa1(Base):
    """2021 Census G01 for Victoria, one row per SA1.

    Only total population is promoted to a column. The other ~105 age/sex/demographic
    columns stay in `payload` so they are queryable without a migration when
    the equity analysis needs them (income, language, disability, etc.).
    """

    __tablename__ = "census_sa1"
    __table_args__ = {"schema": "core"}

    sa1_code: Mapped[str] = mapped_column(String(11), primary_key=True)
    census_year: Mapped[int] = mapped_column(SmallInteger, default=2021)
    population: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
