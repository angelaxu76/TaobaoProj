# barbour/txt_writer.py
# -*- coding: utf-8 -*-
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List
import re

NO_DATA = "No Data"

@dataclass
class OfferLine:
    size: str
    price_gbp: float | int | str
    stock_text: str
    can_order: bool

    def to_line(self) -> str:
        p = str(self.price_gbp).strip()
        return f"{self.size}|{p}|{self.stock_text}|{str(self.can_order)}"


@dataclass
class BarbourTxtRecord:
    product_name: str | None = None
    color_code: str | None = None
    color: str | None = None
    product_description: str | None = None
    gender: str | None = None         # 期望：男款/女款/童款；未知时写 No Data
    material: str | None = None       # 多项用 "; " 连接
    feature: str | None = None        # 多项用 "; " 连接
    category: str | None = None       # 追加：如 waxed jacket / gilet / …
    title: str | None = None          # 追加：用于淘宝标题
    source_url: str | None = None
    site_name: str | None = None
    offers: List[OfferLine] = field(default_factory=list)

    def normalize(self) -> "BarbourTxtRecord":
        def clean(s: str | None) -> str | None:
            if s is None:
                return None
            s = s.strip()
            return s if s else None

        self.product_name = clean(self.product_name)
        self.color_code = clean(self.color_code)
        self.color = clean(self.color)
        self.product_description = clean(self.product_description)
        self.gender = clean(self.gender)
        self.material = clean(self.material)
        self.feature = clean(self.feature)
        self.category = clean(self.category)
        self.title = clean(self.title)
        self.source_url = clean(self.source_url)
        self.site_name = clean(self.site_name)

        # 颜色有时抓到前缀“- ”，清理一下
        if self.color and self.color.startswith("-"):
            self.color = self.color.lstrip("-").strip()

        # Gender 归一：官网风格常用“男款/女款/童款”
        if self.gender:
            g = self.gender.lower()
            if any(k in g for k in ["women", "ladies", "woman", "女"]):
                self.gender = "女款"
            elif any(k in g for k in ["men", "mens", "man", "男"]):
                self.gender = "男款"
            elif any(k in g for k in ["kid", "kids", "boy", "girl", "童"]):
                self.gender = "童款"
            else:
                self.gender = "No Data"

        # 合法化 offers
        fixed: List[OfferLine] = []
        for o in self.offers:
            if not o or not o.size:
                continue
            # 价格转 float/保留原样
            try:
                price = float(str(o.price_gbp).replace(",", "").strip())
            except Exception:
                price = str(o.price_gbp).strip()
            fixed.append(OfferLine(size=o.size.strip(),
                                   price_gbp=price,
                                   stock_text=(o.stock_text or NO_DATA),
                                   can_order=bool(o.can_order)))
        self.offers = fixed
        return self

    def ensure_defaults(self) -> "BarbourTxtRecord":
        # 缺则填 No Data（保持每个字段都有值）
        for f in ["product_name","color_code","color","product_description",
                  "gender","material","feature","category","title",
                  "source_url","site_name"]:
            if getattr(self, f) in (None, ""):
                setattr(self, f, NO_DATA)
        return self

    def to_txt(self) -> str:
        self.normalize().ensure_defaults()
        lines = [
            f"Product Name: {self.product_name}",
            f"Product Code: {self.color_code}",
            f"Product Colour: {self.color}",
            f"Product Description: {self.product_description}",
            f"Product Gender: {self.gender}",
            f"Product Material: {self.material}",
            f"Feature: {self.feature}",
            f"Category: {self.category}",
            f"Title: {self.title}",
            "",
            f"Source URL: {self.source_url}",
            f"Site Name: {self.site_name}",
            "",
            "Offer List:",
        ]
        lines += [o.to_line() for o in self.offers]
        return "\n".join(lines)


def write_barbour_txt(path: str | Path, record: BarbourTxtRecord) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(record.to_txt(), encoding="utf-8")
