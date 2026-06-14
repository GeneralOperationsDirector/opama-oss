export interface CustomField {
  id?: number;
  key: string;
  value: string;
}

export interface CustomAsset {
  id: number;
  user_id: number;
  name: string;
  category: string;
  condition: string | null;
  quantity: number;
  purchase_price: number | null;
  purchase_date: string | null;
  estimated_value: number | null;
  description: string | null;
  image_url: string | null;
  image_thumb_url: string | null;
  back_image_url: string | null;
  back_image_thumb_url: string | null;
  tags: string | null;
  created_at: string;
  updated_at: string;
  custom_fields: CustomField[];
  // Website listing
  listed_on_website: boolean;
  listing_price_cad: number | null;
  shipping_price_cad: number | null;
  website_slug: string | null;
  // Sale recording (set by the storefront webhook — read-only in UI)
  sale_price_cad: number | null;
  sale_date: string | null;
  sale_platform: string | null;
}

export interface PortfolioSummary {
  total_assets: number;
  total_cost: number;
  total_estimated_value: number;
  unrealized_gain: number;
  categories: { category: string; count: number; value: number }[];
}

export type AssetFormData = Omit<CustomAsset, "id" | "created_at" | "updated_at" | "image_thumb_url" | "back_image_thumb_url">;
