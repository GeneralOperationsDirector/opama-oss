"""
Thin wrapper around the Shopify Admin REST API.

Scope is intentionally small — just enough to verify credentials
(`get_shop()`) and publish the opama storefront catalog as Shopify products
(`create_product()` / `update_product()`). No imports from `services.*` or
`app.*` — keeps this file portable if opama_shopify is ever split into its
own repo (see external_plugins/README.md).
"""

from __future__ import annotations

import httpx

API_VERSION = "2024-10"


class ShopifyAPIError(Exception):
    """Raised when the Shopify Admin API returns an error response."""


class ShopifyClient:
    def __init__(self, shop_domain: str, access_token: str, timeout: float = 20.0):
        self.base_url = f"https://{shop_domain}/admin/api/{API_VERSION}"
        self._headers = {
            "X-Shopify-Access-Token": access_token,
            "Content-Type": "application/json",
        }
        self._timeout = timeout

    def get_shop(self) -> dict:
        """GET /shop.json — used to verify shop_domain/access_token."""
        return self._request("GET", "/shop.json")["shop"]

    def create_product(self, product: dict) -> dict:
        return self._request("POST", "/products.json", json={"product": product})["product"]

    def update_product(self, product_id: str, product: dict) -> dict:
        return self._request("PUT", f"/products/{product_id}.json", json={"product": product})["product"]

    def _request(self, method: str, path: str, **kwargs) -> dict:
        resp = httpx.request(
            method, f"{self.base_url}{path}", headers=self._headers, timeout=self._timeout, **kwargs
        )
        if resp.status_code >= 400:
            raise ShopifyAPIError(f"{method} {path} -> {resp.status_code}: {resp.text[:300]}")
        return resp.json()
