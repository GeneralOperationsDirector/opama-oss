// Types mirroring services/vehicles/schemas.py response shapes.

export interface ServiceRecord {
  id: number;
  user_id: number;
  asset_id: number;
  service_date: string | null;
  odometer: number | null;
  service_type: string;
  cost: number | null;
  vendor: string | null;
  notes: string | null;
  document_url: string | null;
  document_filename: string | null;
  created_at: string;
  updated_at: string;
}

export interface VehicleDocument {
  id: number;
  user_id: number;
  asset_id: number;
  doc_type: string;
  issued_date: string | null;
  expiry_date: string | null;
  document_url: string | null;
  document_filename: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface VehicleSummary {
  vehicle_count: number;
  total_service_cost: number;
  service_record_count: number;
  documents_expiring_soon: number;
}

// Payload shapes for create/update requests.
export type ServiceRecordForm = Omit<ServiceRecord, "id" | "user_id" | "document_url" | "document_filename" | "created_at" | "updated_at">;

export type VehicleDocumentForm = Omit<VehicleDocument, "id" | "user_id" | "document_url" | "document_filename" | "created_at" | "updated_at">;
