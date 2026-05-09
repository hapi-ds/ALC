// src/frontend/src/types/report.ts

// ---------------------------------------------------------------------------
// Report API response types
// ---------------------------------------------------------------------------

/** Backend response for a single report */
export interface ReportResponse {
  id: number;
  document_uuid: string;
  template_id: number;
  uploaded_by: number;
  uploaded_at: string | null;
  status: "Draft" | "Extracted" | "Validated";
  field_values: ReportFieldValueResponse[];
}

/** Backend response for a single field value within a report */
export interface ReportFieldValueResponse {
  field_uuid: string;
  value: string | null;
  validated: boolean;
}

// ---------------------------------------------------------------------------
// Report submission payload types
// ---------------------------------------------------------------------------

/** A single field value entry for report creation */
export interface FieldValueEntry {
  field_uuid: string;
  value: string | null;
}

/** Payload sent to POST /api/reports for manual report creation */
export interface ReportCreatePayload {
  document_uuid: string;
  field_values: FieldValueEntry[];
}

// ---------------------------------------------------------------------------
// Comparison types
// ---------------------------------------------------------------------------

/** Response from GET /api/reports/{report_id}/compare */
export interface ComparisonData {
  report_id: number;
  compared_with_report_id: number | null;
  total_fields: number;
  matches: number;
  discrepancies: number;
  rows: ComparisonFieldRow[];
}

/** A single row in the comparison view aligning fields by Field_UUID */
export interface ComparisonFieldRow {
  field_uuid: string;
  field_label: string;
  extracted_value: string | null;
  entered_value: string | null;
  is_match: boolean;
}
