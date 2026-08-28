"""Trade baskets: multiple paper trades grouped under one approved strategy."""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .paper import PaperTradingEngine

_basket_counter = itertools.count(100)


@dataclass
class TradeBasket:
    id: str
    strategy: str
    symbol: str
    direction: str
    max_loss: float
    status: str = "active"       # active | closed
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    position_ids: list[str] = field(default_factory=list)
    closed_pl: float = 0.0

    def as_dict(self) -> dict:
        return self.__dict__.copy()


class BasketManager:
    def __init__(self, paper: PaperTradingEngine) -> None:
        self.paper = paper
        self.baskets: dict[str, TradeBasket] = {}

    def create(self, strategy: str, symbol: str, direction: str, max_loss: float) -> TradeBasket:
        basket = TradeBasket(
            id=f"ARES-{next(_basket_counter)}",
            strategy=strategy, symbol=symbol, direction=direction, max_loss=max_loss,
        )
        self.baskets[basket.id] = basket
        return basket

    def find(self, basket_id: str) -> TradeBasket | None:
        # Accept "ARES-104", "#ARES-104", "104"
        key = basket_id.strip().lstrip("#").upper()
        if not key.startswith("ARES-"):
            key = f"ARES-{key}"
        return self.baskets.get(key)

    def basket_view(self, basket: TradeBasket) -> dict:
        open_positions = [
            p.as_dict() for p in self.paper.positions.values() if p.basket_id == basket.id
        ]
        closed = [t for t in self.paper.history if t.basket_id == basket.id]
        floating = sum(p["floating_pl"] for p in open_positions)
        closed_pl = sum(t.pl for t in closed)
        view = basket.as_dict()
        view.update({
            "open_trades": len(open_positions),
            "closed_trades": len(closed),
            "combined_exposure_lots": round(sum(p["volume"] for p in open_positions), 2),
            "combined_pl": round(floating + closed_pl, 2),
            "positions": open_positions,
        })
        if not open_positions and (closed or basket.status == "closed"):
            view["status"] = basket.status = "closed"
            basket.closed_pl = round(closed_pl, 2)
        return view

    def list_views(self) -> list[dict]:
        return [self.basket_view(b) for b in self.baskets.values()]

    async def close_basket(self, basket_id: str) -> dict:
        basket = self.find(basket_id)
        if basket is None:
            return {"success": False, "message": f"Basket {basket_id} not found"}
        results = []
        for pos in [p for p in list(self.paper.positions.values()) if p.basket_id == basket.id]:
            result = await self.paper.close_position(pos.id, reason=f"basket {basket.id} closed")
            results.append(result.as_dict())
        basket.status = "closed"
        return {"success": True, "message": f"Basket {basket.id} closed",
                "closed": results, "basket": self.basket_view(basket)}

    async def enforce_max_loss(self) -> list[str]:
        """Close any active basket whose combined P/L breaches its max loss."""
        closed = []
        for basket in list(self.baskets.values()):
            if basket.status != "active":
                continue
            view = self.basket_view(basket)
            if view["combined_pl"] <= -abs(basket.max_loss) and view["open_trades"] > 0:
                await self.close_basket(basket.id)
                closed.append(basket.id)
        return closed
