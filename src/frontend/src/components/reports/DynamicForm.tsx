import { useState, useCallback, useMemo } from "react";
import { Button } from "@/components/ui/button";
import { Loader2 } from "lucide-react";
import {
  TextField,
  FloatField,
  IntegerField,
  DateField,
  BooleanField,
  ContentBlock,
} from "./fields";
import {
  validateField,
  validateAllFields,
} from "@/lib/reportValidation";
import type { ValidationRule } from "@/lib/reportValidation";
import type {
  SerializedElement,
  SerializedFieldElement,
  TextFieldConfig,
  FloatFieldConfig,
  IntegerFieldConfig,
  DateFieldConfig,
  BooleanFieldConfig,
} from "@/types/template";
import type { TemplateFieldResponse } from "@/types/template";
import type { FieldValueEntry } from "@/types/report";

export interface DynamicFormProps {
  elements: SerializedElement[];
  templateFields: TemplateFieldResponse[];
  onSubmit: (fieldValues: FieldValueEntry[]) => void;
  isSubmitting: boolean;
  serverErrors?: Record<string, string>;
}

/**
 * Dynamic form component that renders typed field inputs and content blocks
 * from a template's elements array. Manages internal form state, validates
 * on blur, and disables submit when errors exist.
 */
export function DynamicForm({
  elements,
  templateFields,
  onSubmit,
  isSubmitting,
  serverErrors,
}: DynamicFormProps) {
  // Build initial values from default_value in elements
  const initialValues = useMemo(() => {
    const vals: Record<string, string> = {};
    for (const el of elements) {
      if (el.element_type === "field") {
        const field = el as SerializedFieldElement;
        const tf = templateFields.find((f) => f.field_label === field.label);
        const key = tf?.field_uuid ?? field.label;
        vals[key] = field.default_value ?? "";
      }
    }
    return vals;
  }, [elements, templateFields]);

  const [values, setValues] = useState<Record<string, string>>(initialValues);
  const [touchedFields, setTouchedFields] = useState<Set<string>>(new Set());
  const [errors, setErrors] = useState<Record<string, string>>({});

  // Build validation rules from elements + templateFields
  const rules: ValidationRule[] = useMemo(() => {
    return elements
      .filter((el) => el.element_type === "field")
      .map((el) => {
        const field = el as SerializedFieldElement;
        const tf = templateFields.find((f) => f.field_label === field.label);
        return {
          fieldUuid: tf?.field_uuid ?? field.label,
          fieldType: field.type,
          required: field.required,
          config: field.config as Record<string, unknown>,
        };
      });
  }, [elements, templateFields]);

  const handleChange = useCallback((fieldUuid: string, value: string) => {
    setValues((prev) => ({ ...prev, [fieldUuid]: value }));
  }, []);

  const handleBlur = useCallback(
    (fieldUuid: string) => {
      setTouchedFields((prev) => new Set(prev).add(fieldUuid));

      const rule = rules.find((r) => r.fieldUuid === fieldUuid);
      if (rule) {
        const value = values[fieldUuid] ?? "";
        const error = validateField(value, rule);
        setErrors((prev) => {
          const next = { ...prev };
          if (error) {
            next[fieldUuid] = error;
          } else {
            delete next[fieldUuid];
          }
          return next;
        });
      }
    },
    [rules, values]
  );

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();

      // Validate all fields on submit (forceAll=true)
      const allErrors = validateAllFields(
        values,
        rules,
        touchedFields,
        true
      );
      setErrors(allErrors);

      if (Object.keys(allErrors).length > 0) {
        return;
      }

      // Build field values payload
      const fieldValues: FieldValueEntry[] = rules.map((rule) => ({
        field_uuid: rule.fieldUuid,
        value: values[rule.fieldUuid] || null,
      }));

      onSubmit(fieldValues);
    },
    [values, rules, touchedFields, onSubmit]
  );

  // Merge server errors with client errors
  const displayErrors = useMemo(() => {
    return { ...errors, ...serverErrors };
  }, [errors, serverErrors]);

  const hasErrors = Object.keys(displayErrors).length > 0;

  return (
    <form onSubmit={handleSubmit} className="space-y-4" noValidate>
      {elements.map((element, index) => {
        if (element.element_type === "content_block") {
          return (
            <ContentBlock
              key={`content-${index}`}
              blockType={element.content_type}
              text={element.text}
            />
          );
        }

        const field = element as SerializedFieldElement;
        const tf = templateFields.find((f) => f.field_label === field.label);
        const fieldUuid = tf?.field_uuid ?? field.label;
        const value = values[fieldUuid] ?? "";
        const error = displayErrors[fieldUuid] ?? null;

        const baseProps = {
          fieldUuid,
          label: field.label,
          required: field.required,
          helpText: field.help_text,
          defaultValue: field.default_value,
          value,
          onChange: (v: string) => handleChange(fieldUuid, v),
          onBlur: () => handleBlur(fieldUuid),
          error,
          disabled: isSubmitting,
        };

        switch (field.type) {
          case "Text":
            return (
              <TextField
                key={fieldUuid}
                {...baseProps}
                config={field.config as TextFieldConfig}
              />
            );
          case "Float":
            return (
              <FloatField
                key={fieldUuid}
                {...baseProps}
                config={field.config as FloatFieldConfig}
              />
            );
          case "Integer":
            return (
              <IntegerField
                key={fieldUuid}
                {...baseProps}
                config={field.config as IntegerFieldConfig}
              />
            );
          case "Date":
            return (
              <DateField
                key={fieldUuid}
                {...baseProps}
                config={field.config as DateFieldConfig}
              />
            );
          case "Boolean":
            return (
              <BooleanField
                key={fieldUuid}
                {...baseProps}
                config={field.config as BooleanFieldConfig}
              />
            );
          default:
            return null;
        }
      })}

      <div className="pt-4">
        <Button
          type="submit"
          disabled={isSubmitting || hasErrors}
          className="w-full"
        >
          {isSubmitting ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              Submitting…
            </>
          ) : (
            "Submit Report"
          )}
        </Button>
      </div>
    </form>
  );
}
