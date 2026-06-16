export interface StorefrontSettings {
  id: number;
  user_id: number;
  site_name: string;
  site_url: string;
  public_api_url: string;
  catalog_path: string | null;
  webhook_url: string | null;
  last_published_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface StorefrontListing {
  id: number;
  name: string;
  category: string;
  condition: string | null;
  image_url: string | null;
  image_thumb_url: string | null;
  back_image_url: string | null;
  listing_price_cad: number | null;
  shipping_price_cad: number | null;
  website_slug: string | null;
  marketplace_ebay: string | null;
  marketplace_facebook: string | null;
  marketplace_kijiji: string | null;
  marketplace_craigslist: string | null;
  sale_date: string | null;
  sale_price_cad: number | null;
  sale_platform: string | null;
  listed_on_website: boolean;
  _catalog_preview: CatalogEntry;
}

export interface CatalogEntry {
  id: string;
  title: string;
  category: string;
  condition: string;
  description: string;
  priceCad: number;
  shippingCad: number;
  images: string[];
  sold: boolean;
  marketplaceLinks: Record<string, string>;
}

export interface SalesData {
  total_revenue_cad: number;
  total_sold: number;
  by_platform: Record<string, number>;
  items: StorefrontListing[];
}

export interface GitHubTestResult {
  connected: boolean;
  repo_full_name?: string | null;
  private?: boolean | null;
  can_push?: boolean | null;
  error?: string | null;
}

// ---------------------------------------------------------------------------
// GitHub Publishing (services/github_publish/ — mounted at /integrations/github)
// ---------------------------------------------------------------------------

export interface GitHubPublishSettings {
  repo: string | null;
  file_path: string | null;
  commit_message: string | null;
  // Token is never returned in full — only a masked hint and a boolean
  token_set: boolean;
  token_hint: string | null;
}

export interface ImageUrlTestResult {
  reachable: boolean;
  tested_url: string;
  status_code?: number | null;
  content_type?: string | null;
  error?: string | null;
}

export interface PublishResult {
  published: boolean;
  item_count: number;
  sold_count: number;
  last_published_at: string | null;
  error: string | null;
  catalog: CatalogEntry[];
  github_commit_url: string | null;
}

// ---------------------------------------------------------------------------
// Shopify (external plugin — external_plugins/opama_shopify/)
// ---------------------------------------------------------------------------

export interface ShopifySettings {
  id: number;
  user_id: number;
  shop_domain: string;
  // Token is never returned in full — only a masked hint and a boolean
  access_token_set: boolean;
  access_token_hint: string | null;
  last_published_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ShopifyProductImage {
  src: string;
}

export interface ShopifyProductVariant {
  price: string;
  sku: string;
  inventory_management: string | null;
}

export interface ShopifyProduct {
  title: string;
  body_html: string;
  vendor: string;
  product_type: string;
  tags: string;
  status: string;
  images: ShopifyProductImage[];
  variants: ShopifyProductVariant[];
}

export interface ShopifyPublishPreview {
  item_count: number;
  skipped_sold_count: number;
  products: ShopifyProduct[];
}

export interface ShopifyPublishResult {
  published: boolean;
  created_count: number;
  updated_count: number;
  skipped_count: number;
  error: string | null;
  errors: string[];
}

export interface ShopifyTestResult {
  connected: boolean;
  shop_name?: string;
  domain?: string;
}
