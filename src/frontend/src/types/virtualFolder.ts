export interface TagFilter {
  tags?: string[];
  status?: string;
}

export interface VirtualFolderResponse {
  id: number;
  name: string;
  tag_filter: TagFilter;
  sort_order: string;
  is_system_default: boolean;
  created_by: number;
  created_at: string | null;
}

export interface VirtualFolderCreate {
  name: string;
  tag_filter: TagFilter;
  sort_order: string;
}

export interface VirtualFolderUpdate {
  name?: string;
  tag_filter?: TagFilter;
  sort_order?: string;
}
