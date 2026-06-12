import { useCallback } from "react";
import { Plus, Trash2 } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import type { TraceabilityTargetType } from "@/types/literatureSearch";

/** A single traceability link entry with target type and ID. */
export interface TraceabilityLinkEntry {
  target_type: TraceabilityTargetType;
  target_id: string;
}

interface TraceabilityLinkSelectorProps {
  /** Current list of link entries */
  value: TraceabilityLinkEntry[];
  /** Callback when the list changes */
  onChange: (entries: TraceabilityLinkEntry[]) => void;
  /** Optional disabled state */
  disabled?: boolean;
  /** Maximum number of entries allowed (default 20) */
  max?: number;
}

/**
 * TraceabilityLinkSelector allows users to add target_type / target_id pairs
 * for linking internalized documents to requirements or test cases.
 * Kept intentionally simple — no autocomplete from TraceabilityMatrix since
 * the data isn't readily accessible from this context.
 *
 * Validates: Requirements 4.1, 6.1
 */
export function TraceabilityLinkSelector({
  value,
  onChange,
  disabled = false,
  max = 20,
}: TraceabilityLinkSelectorProps) {
  const handleAdd = useCallback(() => {
    if (value.length >= max) return;
    onChange([...value, { target_type: "requirement", target_id: "" }]);
  }, [value, onChange, max]);

  const handleRemove = useCallback(
    (index: number) => {
      onChange(value.filter((_, i) => i !== index));
    },
    [value, onChange],
  );

  const handleTypeChange = useCallback(
    (index: number, target_type: TraceabilityTargetType) => {
      const updated = [...value];
      updated[index] = { ...updated[index], target_type };
      onChange(updated);
    },
    [value, onChange],
  );

  const handleIdChange = useCallback(
    (index: number, target_id: string) => {
      const updated = [...value];
      updated[index] = { ...updated[index], target_id };
      onChange(updated);
    },
    [value, onChange],
  );

  return (
    <div className="space-y-2">
      {value.map((entry, index) => (
        <div key={index} className="flex items-center gap-2">
          <Select
            value={entry.target_type}
            onChange={(e) =>
              handleTypeChange(
                index,
                e.target.value as TraceabilityTargetType,
              )
            }
            disabled={disabled}
            aria-label={`Link ${index + 1} target type`}
            className="w-40"
          >
            <option value="requirement">Requirement</option>
            <option value="test_case">Test Case</option>
          </Select>
          <Input
            type="text"
            placeholder="Target ID"
            value={entry.target_id}
            onChange={(e) => handleIdChange(index, e.target.value)}
            disabled={disabled}
            aria-label={`Link ${index + 1} target ID`}
            className="flex-1"
          />
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={() => handleRemove(index)}
            disabled={disabled}
            aria-label={`Remove link ${index + 1}`}
          >
            <Trash2 className="h-4 w-4" aria-hidden="true" />
          </Button>
        </div>
      ))}
      {value.length < max && (
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={handleAdd}
          disabled={disabled}
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          Add Link
        </Button>
      )}
    </div>
  );
}
