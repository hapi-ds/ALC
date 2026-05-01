import { create } from "zustand";

interface TemplateField {
  field_uuid: string;
  field_type: string;
  field_label: string;
  field_order: number;
}

interface Template {
  id: number;
  document_uuid: string;
  name: string;
  status: string;
  fields: TemplateField[];
}

interface TemplateState {
  templates: Template[];
  selectedTemplate: Template | null;
  isLoading: boolean;
  fetchTemplates: () => Promise<void>;
  fetchTemplate: (uuid: string) => Promise<void>;
  createTemplate: (name: string, fields: Omit<TemplateField, "field_uuid">[]) => Promise<void>;
  downloadPdf: (uuid: string) => Promise<void>;
}

export const useTemplateStore = create<TemplateState>((set) => ({
  templates: [],
  selectedTemplate: null,
  isLoading: false,

  fetchTemplates: async () => {
    set({ isLoading: true });
    // Placeholder: GET /api/templates
    set({ templates: [], isLoading: false });
  },

  fetchTemplate: async (_uuid) => {
    set({ isLoading: true });
    // Placeholder: GET /api/templates/{uuid}
    set({ selectedTemplate: null, isLoading: false });
  },

  createTemplate: async (_name, _fields) => {
    // Placeholder: POST /api/templates
  },

  downloadPdf: async (_uuid) => {
    // Placeholder: POST /api/templates/{uuid}/download-pdf
  },
}));
