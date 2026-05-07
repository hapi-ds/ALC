// src/frontend/src/types/template.ts

/** Supported field types matching backend Literal type */
export type FieldType = "Text" | "Float" | "Integer" | "Date" | "Boolean";

/** Client-side canvas field representation */
export interface CanvasFieldData {
  id: string;              // Client-generated UUID v4 (temporary)
  label: string;           // User-editable label (1-200 chars)
  type: FieldType;         // Field data type
  fieldOrder: number;      // 0-based display order
}

/** Template creation payload sent to POST /api/templates */
export interface TemplateCreatePayload {
  name: string;
  json_schema: {
    fields: Array<{
      label: string;
      type: FieldType;
    }>;
  };
  user_id: number;
}

/** Backend template response (from GET /api/templates and POST /api/templates) */
export interface TemplateResponse {
  id: number;
  document_uuid: string;
  name: string;
  json_schema: Record<string, unknown>;
  status: string;
  created_by: number;
  fields: TemplateFieldResponse[];
}

/** Backend field response */
export interface TemplateFieldResponse {
  id: number;
  field_uuid: string;
  field_type: string;
  field_label: string;
  field_order: number;
}
