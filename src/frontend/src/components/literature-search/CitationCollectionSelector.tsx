import { useState, useEffect, useCallback } from "react";
import { Select } from "@/components/ui/select";
import { useCitationCollections } from "@/hooks/useLiteratureSearch";
import type { CitationCollection } from "@/types/literatureSearch";

interface CitationCollectionSelectorProps {
  /** Currently selected collection ID (null means "Add to none") */
  value: number | null;
  /** Callback when selection changes */
  onChange: (collectionId: number | null) => void;
  /** Optional disabled state */
  disabled?: boolean;
}

/**
 * CitationCollectionSelector is a dropdown listing available citation collections.
 * Includes a "No collection" option and fetches available collections on mount.
 *
 * Validates: Requirements 5.1, 5.2
 */
export function CitationCollectionSelector({
  value,
  onChange,
  disabled = false,
}: CitationCollectionSelectorProps) {
  const { list, loading } = useCitationCollections();
  const [collections, setCollections] = useState<CitationCollection[]>([]);

  const loadCollections = useCallback(async () => {
    const results = await list();
    setCollections(results);
  }, [list]);

  useEffect(() => {
    loadCollections();
  }, [loadCollections]);

  const handleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const selectedValue = e.target.value;
    onChange(selectedValue === "" ? null : Number(selectedValue));
  };

  return (
    <Select
      value={value != null ? String(value) : ""}
      onChange={handleChange}
      disabled={disabled || loading}
      aria-label="Citation collection"
    >
      <option value="">No collection</option>
      {collections.map((collection) => (
        <option key={collection.id} value={String(collection.id)}>
          {collection.name}
        </option>
      ))}
    </Select>
  );
}
