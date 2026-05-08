// src/frontend/src/types/template.ts

/** Supported field types matching backend Literal type */
export type FieldType = "Text" | "Float" | "Integer" | "Date" | "Boolean";

/** Element type discriminator for canvas items */
export type ElementType = "field" | "content_block";

/** Content block types for non-editable template elements */
export type ContentBlockType =
  | "heading_h1"
  | "heading_h2"
  | "heading_h3"
  | "paragraph"
  | "divider";

// ---------------------------------------------------------------------------
// Type-specific field configuration interfaces
// ---------------------------------------------------------------------------

/** Configuration for Text fields */
export interface TextFieldConfig {
  min_length?: number;
  max_length?: number;
  placeholder?: string;
  regex_pattern?: string;
}

/** Configuration for Float fields */
export interface FloatFieldConfig {
  decimal_precision?: number;
  min_value?: number;
  max_value?: number;
  unit_label?: string;
}

/** Configuration for Integer fields */
export interface IntegerFieldConfig {
  min_value?: number;
  max_value?: number;
  step_size?: number;
  unit_label?: string;
}

/** Configuration for Date fields */
export interface DateFieldConfig {
  min_date?: string;
  max_date?: string;
  date_format?: "YYYY-MM-DD" | "DD/MM/YYYY" | "MM/DD/YYYY" | "DD-MMM-YYYY";
}

/** Configuration for Boolean fields */
export interface BooleanFieldConfig {
  true_label?: string;
  false_label?: string;
}

/** Union of all type-specific field configurations */
export type FieldConfig =
  | TextFieldConfig
  | FloatFieldConfig
  | IntegerFieldConfig
  | DateFieldConfig
  | BooleanFieldConfig;

// ---------------------------------------------------------------------------
// Canvas element types (enhanced)
// ---------------------------------------------------------------------------

/** Base interface for all canvas elements */
export interface CanvasElementBase {
  id: string;
  element_type: ElementType;
  fieldOrder: number;
}

/** Canvas field element with rich configuration */
export interface CanvasFieldElement extends CanvasElementBase {
  element_type: "field";
  label: string;
  type: FieldType;
  required: boolean;
  help_text: string | null;
  default_value: string | null;
  config: FieldConfig;
}

/** Canvas content block element */
export interface CanvasContentBlockElement extends CanvasElementBase {
  element_type: "content_block";
  content_type: ContentBlockType;
  text: string | null;
}

/** Union type for all canvas items (fields and content blocks) */
export type CanvasItem = CanvasFieldElement | CanvasContentBlockElement;

// ---------------------------------------------------------------------------
// Serialization types (payload sent to backend)
// ---------------------------------------------------------------------------

/** Serialized field element for backend payload */
export interface SerializedFieldElement {
  element_type: "field";
  label: string;
  type: FieldType;
  required: boolean;
  help_text: string | null;
  default_value: string | null;
  config: FieldConfig;
}

/** Serialized content block element for backend payload */
export interface SerializedContentBlockElement {
  element_type: "content_block";
  content_type: ContentBlockType;
  text: string | null;
}

/** Union of serialized element types */
export type SerializedElement =
  | SerializedFieldElement
  | SerializedContentBlockElement;

// ---------------------------------------------------------------------------
// Version types
// ---------------------------------------------------------------------------

/** Payload for creating a new template version */
export interface VersionCreatePayload {
  json_schema: {
    elements: SerializedElement[];
  };
  user_id: number;
}

/** Backend response for a template version */
export interface TemplateVersionResponse {
  id: number;
  version_number: number;
  document_uuid: string;
  json_schema: Record<string, unknown>;
  status: string;
  is_active: boolean;
  created_by: number;
  change_reason: string;
  created_at: string;
  fields: TemplateVersionFieldResponse[];
}

/** Backend response for a field within a template version */
export interface TemplateVersionFieldResponse {
  id: number;
  field_uuid: string;
  field_type: string;
  field_label: string;
  field_order: number;
  element_type: ElementType;
  content_type: ContentBlockType | null;
  text_content: string | null;
  config: Record<string, unknown> | null;
  required: boolean;
  help_text: string | null;
  default_value: string | null;
}

// ---------------------------------------------------------------------------
// Legacy types (preserved for backward compatibility during migration)
// ---------------------------------------------------------------------------

/**
 * @deprecated Use CanvasFieldElement instead. Preserved for backward
 * compatibility during migration to the enhanced element system.
 */
export interface CanvasFieldData {
  id: string;              // Client-generated UUID v4 (temporary)
  label: string;           // User-editable label (1-200 chars)
  type: FieldType;         // Field data type
  fieldOrder: number;      // 0-based display order
}

/** Template creation payload sent to POST /api/templates (enhanced elements format) */
export interface TemplateCreatePayload {
  name: string;
  json_schema: {
    elements: SerializedElement[];
  };
  user_id: number;
}

/**
 * @deprecated Legacy payload format with `fields` key. Preserved for backward
 * compatibility with existing tests during migration.
 */
export interface LegacyTemplateCreatePayload {
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
