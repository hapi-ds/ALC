export interface AuditEvent {
  transaction_id: number;
  timestamp: string;
  user_id: number;
  user_display_name: string | null;
  record_type: string;
  record_id: number;
  operation_type: "INSERT" | "UPDATE" | "DELETE";
  change_reason: string | null;
  changed_fields: string[];
  total_changed_fields: number;
  company_id: number;
}

export interface AuditTrailFilters {
  user_id?: number;
  date_start?: string;
  date_end?: string;
  record_type?: string;
  operation_type?: "INSERT" | "UPDATE" | "DELETE";
}

export interface AuditTrailPage {
  events: AuditEvent[];
  next_cursor: string | null;
  total_count: number;
  warnings?: string[];
}

export interface FieldChange {
  field_name: string;
  old_value: unknown;
  new_value: unknown;
}

export interface AuditEventDetail {
  transaction_id: number;
  timestamp: string;
  user_id: number;
  user_display_name: string | null;
  record_type: string;
  record_id: number;
  operation_type: "INSERT" | "UPDATE" | "DELETE";
  change_reason: string | null;
  field_changes: FieldChange[];
  company_id: number;
}

export interface ExportStatus {
  job_id: string;
  status: "pending" | "processing" | "completed" | "failed";
  download_url?: string;
  error_message?: string;
}

export interface SortConfig {
  column: string;
  direction: "asc" | "desc";
}
