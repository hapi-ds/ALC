export interface DocumentTag {
  id: number;
  tag: string;
}

export interface DocumentVersion {
  id: number;
  major_version: number;
  minor_version: number;
  storage_key: string;
  file_hash: string;
  uploaded_by: number;
  uploaded_at: string;
  change_reason: string | null;
}

export interface DocumentResponse {
  id: number;
  document_uuid: string;
  title: string;
  folder_path: string;
  document_type: string;
  current_status: string;
  created_by: number;
  created_at: string;
  tags: DocumentTag[];
  versions: DocumentVersion[];
}

export interface DocumentSearchResponse {
  items: DocumentResponse[];
  total: number;
}

export interface UploadFormData {
  file: File;
  title: string;
  folder_path: string;
  document_type: string;
  tags: string; // comma-separated
}

export interface VersionUploadFormData {
  file: File;
  version_type: "major" | "minor";
  change_reason: string;
}
