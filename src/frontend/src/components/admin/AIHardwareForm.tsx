import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { Save, AlertTriangle, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useSystemConfigStore } from "@/stores/useSystemConfigStore";
import type { AIHardwareUpdate } from "@/types/systemConfig";

/**
 * AIHardwareForm — displays and edits the current AI model configuration.
 *
 * Shows chat model, embedding model, OCR model settings, inference mode,
 * GPU device ID, and vLLM URLs. Uses react-hook-form for validation.
 * On submit, prompts for X-Change-Reason and displays a "restart required"
 * indicator when config changes need a vLLM restart.
 */
export function AIHardwareForm() {
  const { aiHardware, loading, errors, fetchAIHardware, updateAIHardware } =
    useSystemConfigStore();

  const [showReasonDialog, setShowReasonDialog] = useState(false);
  const [reason, setReason] = useState("");
  const [restartRequired, setRestartRequired] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors: formErrors, isDirty },
  } = useForm<AIHardwareUpdate>();

  useEffect(() => {
    fetchAIHardware();
  }, [fetchAIHardware]);

  useEffect(() => {
    if (aiHardware) {
      reset({
        model_chat_name: aiHardware.model_chat_name,
        model_chat_path: aiHardware.model_chat_path,
        model_chat_max_gpu_memory_gb: aiHardware.model_chat_max_gpu_memory_gb,
        model_embedding_name: aiHardware.model_embedding_name,
        model_embedding_path: aiHardware.model_embedding_path,
        model_embedding_dimension: aiHardware.model_embedding_dimension,
        model_ocr_name: aiHardware.model_ocr_name,
        model_ocr_path: aiHardware.model_ocr_path,
        inference_mode: aiHardware.inference_mode,
        gpu_device_id: aiHardware.gpu_device_id,
      });
    }
  }, [aiHardware, reset]);

  const onFormSubmit = () => {
    setShowReasonDialog(true);
  };

  const handleConfirmSubmit = async (data: AIHardwareUpdate) => {
    if (reason.trim().length < 1) return;

    setSubmitError(null);
    try {
      await updateAIHardware(data, reason.trim());
      setRestartRequired(true);
      setShowReasonDialog(false);
      setReason("");
    } catch (err) {
      setSubmitError(
        err instanceof Error ? err.message : "Failed to update AI hardware config"
      );
      setShowReasonDialog(false);
      setReason("");
    }
  };

  const isLoading = loading["aiHardware"];
  const fetchError = errors["aiHardware"];

  if (isLoading && !aiHardware) {
    return (
      <div className="space-y-4 animate-pulse" aria-label="Loading AI hardware configuration">
        <div className="h-6 w-1/3 rounded bg-muted" />
        <div className="h-4 w-2/3 rounded bg-muted" />
        <div className="h-4 w-1/2 rounded bg-muted" />
      </div>
    );
  }

  if (fetchError && !aiHardware) {
    return (
      <div className="rounded-md border border-red-200 bg-red-50 p-4" role="alert">
        <div className="flex items-center gap-2">
          <AlertTriangle className="h-5 w-5 text-red-600" aria-hidden="true" />
          <p className="text-sm font-medium text-red-800">
            Failed to load AI hardware configuration
          </p>
        </div>
        <p className="mt-1 text-sm text-red-700">{fetchError}</p>
        <Button
          variant="outline"
          size="sm"
          className="mt-3"
          onClick={() => fetchAIHardware()}
        >
          Retry
        </Button>
      </div>
    );
  }

  if (!aiHardware) return null;

  return (
    <div className="space-y-6">
      {/* Restart required banner */}
      {restartRequired && (
        <div
          className="flex items-center gap-2 rounded-md border border-amber-200 bg-amber-50 px-4 py-3"
          role="alert"
        >
          <AlertTriangle className="h-5 w-5 text-amber-600" aria-hidden="true" />
          <p className="text-sm font-medium text-amber-800">
            Configuration updated. A vLLM service restart is required for changes to take effect.
          </p>
        </div>
      )}

      <form
        onSubmit={handleSubmit(onFormSubmit)}
        className="space-y-6"
        aria-label="AI hardware configuration form"
      >
        {/* Chat Model Section */}
        <fieldset className="space-y-4 rounded-md border border-border p-4">
          <legend className="px-2 text-sm font-semibold text-foreground">
            Chat Model
          </legend>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label
                htmlFor="model_chat_name"
                className="block text-sm font-medium text-foreground"
              >
                Model Name
              </label>
              <input
                id="model_chat_name"
                type="text"
                {...register("model_chat_name")}
                className="mt-1 block w-full rounded-md border border-border bg-background px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>

            <div>
              <label
                htmlFor="model_chat_path"
                className="block text-sm font-medium text-foreground"
              >
                Model Path
              </label>
              <input
                id="model_chat_path"
                type="text"
                {...register("model_chat_path")}
                className="mt-1 block w-full rounded-md border border-border bg-background px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>

            <div>
              <label
                htmlFor="model_chat_max_gpu_memory_gb"
                className="block text-sm font-medium text-foreground"
              >
                Max GPU Memory (GB)
              </label>
              <input
                id="model_chat_max_gpu_memory_gb"
                type="number"
                {...register("model_chat_max_gpu_memory_gb", {
                  valueAsNumber: true,
                  validate: (value) =>
                    value === undefined ||
                    value === null ||
                    value > 0 ||
                    "GPU memory must be a positive integer",
                })}
                className="mt-1 block w-full rounded-md border border-border bg-background px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
              />
              {formErrors.model_chat_max_gpu_memory_gb && (
                <p className="mt-1 text-xs text-red-600" role="alert">
                  {formErrors.model_chat_max_gpu_memory_gb.message}
                </p>
              )}
            </div>
          </div>
        </fieldset>

        {/* Embedding Model Section */}
        <fieldset className="space-y-4 rounded-md border border-border p-4">
          <legend className="px-2 text-sm font-semibold text-foreground">
            Embedding Model
          </legend>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label
                htmlFor="model_embedding_name"
                className="block text-sm font-medium text-foreground"
              >
                Model Name
              </label>
              <input
                id="model_embedding_name"
                type="text"
                {...register("model_embedding_name")}
                className="mt-1 block w-full rounded-md border border-border bg-background px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>

            <div>
              <label
                htmlFor="model_embedding_path"
                className="block text-sm font-medium text-foreground"
              >
                Model Path
              </label>
              <input
                id="model_embedding_path"
                type="text"
                {...register("model_embedding_path")}
                className="mt-1 block w-full rounded-md border border-border bg-background px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>

            <div>
              <label
                htmlFor="model_embedding_dimension"
                className="block text-sm font-medium text-foreground"
              >
                Vector Dimension
              </label>
              <input
                id="model_embedding_dimension"
                type="number"
                {...register("model_embedding_dimension", {
                  valueAsNumber: true,
                  validate: (value) =>
                    value === undefined ||
                    value === null ||
                    value > 0 ||
                    "Dimension must be a positive integer",
                })}
                className="mt-1 block w-full rounded-md border border-border bg-background px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
              />
              {formErrors.model_embedding_dimension && (
                <p className="mt-1 text-xs text-red-600" role="alert">
                  {formErrors.model_embedding_dimension.message}
                </p>
              )}
            </div>
          </div>
        </fieldset>

        {/* OCR Model Section */}
        <fieldset className="space-y-4 rounded-md border border-border p-4">
          <legend className="px-2 text-sm font-semibold text-foreground">
            OCR / Vision Model
          </legend>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label
                htmlFor="model_ocr_name"
                className="block text-sm font-medium text-foreground"
              >
                Model Name
              </label>
              <input
                id="model_ocr_name"
                type="text"
                {...register("model_ocr_name")}
                className="mt-1 block w-full rounded-md border border-border bg-background px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>

            <div>
              <label
                htmlFor="model_ocr_path"
                className="block text-sm font-medium text-foreground"
              >
                Model Path
              </label>
              <input
                id="model_ocr_path"
                type="text"
                {...register("model_ocr_path")}
                className="mt-1 block w-full rounded-md border border-border bg-background px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>
          </div>
        </fieldset>

        {/* Inference Settings Section */}
        <fieldset className="space-y-4 rounded-md border border-border p-4">
          <legend className="px-2 text-sm font-semibold text-foreground">
            Inference Settings
          </legend>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label
                htmlFor="inference_mode"
                className="block text-sm font-medium text-foreground"
              >
                Inference Mode
              </label>
              <select
                id="inference_mode"
                {...register("inference_mode")}
                className="mt-1 block w-full rounded-md border border-border bg-background px-3 py-2 text-sm shadow-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
              >
                <option value="gpu">GPU</option>
                <option value="cpu">CPU</option>
                <option value="mock">Mock</option>
              </select>
            </div>

            <div>
              <label
                htmlFor="gpu_device_id"
                className="block text-sm font-medium text-foreground"
              >
                GPU Device ID
              </label>
              <input
                id="gpu_device_id"
                type="number"
                {...register("gpu_device_id", {
                  valueAsNumber: true,
                  validate: (value) =>
                    value === undefined ||
                    value === null ||
                    value >= 0 ||
                    "GPU device ID must be non-negative",
                })}
                className="mt-1 block w-full rounded-md border border-border bg-background px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
              />
              {formErrors.gpu_device_id && (
                <p className="mt-1 text-xs text-red-600" role="alert">
                  {formErrors.gpu_device_id.message}
                </p>
              )}
            </div>
          </div>
        </fieldset>

        {/* vLLM URLs (read-only display) */}
        <fieldset className="space-y-4 rounded-md border border-border p-4">
          <legend className="px-2 text-sm font-semibold text-foreground">
            vLLM Connection
          </legend>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <span className="block text-sm font-medium text-muted-foreground">
                Chat/OCR URL
              </span>
              <p className="mt-1 text-sm font-mono text-foreground">
                {aiHardware.vllm_chat_url}
              </p>
              <span
                className={`mt-1 inline-flex items-center gap-1 text-xs font-medium ${
                  aiHardware.vllm_chat_status === "reachable"
                    ? "text-green-600"
                    : "text-red-600"
                }`}
              >
                <span
                  className={`h-2 w-2 rounded-full ${
                    aiHardware.vllm_chat_status === "reachable"
                      ? "bg-green-500"
                      : "bg-red-500"
                  }`}
                  aria-hidden="true"
                />
                {aiHardware.vllm_chat_status === "reachable"
                  ? "Reachable"
                  : "Unreachable"}
              </span>
            </div>

            <div>
              <span className="block text-sm font-medium text-muted-foreground">
                Embedding URL
              </span>
              <p className="mt-1 text-sm font-mono text-foreground">
                {aiHardware.vllm_embedding_url}
              </p>
              <span
                className={`mt-1 inline-flex items-center gap-1 text-xs font-medium ${
                  aiHardware.vllm_embedding_status === "reachable"
                    ? "text-green-600"
                    : "text-red-600"
                }`}
              >
                <span
                  className={`h-2 w-2 rounded-full ${
                    aiHardware.vllm_embedding_status === "reachable"
                      ? "bg-green-500"
                      : "bg-red-500"
                  }`}
                  aria-hidden="true"
                />
                {aiHardware.vllm_embedding_status === "reachable"
                  ? "Reachable"
                  : "Unreachable"}
              </span>
            </div>
          </div>
        </fieldset>

        {/* Submit error */}
        {submitError && (
          <p className="text-sm text-red-600" role="alert">
            {submitError}
          </p>
        )}

        {/* Submit button */}
        <div className="flex items-center gap-3">
          <Button type="submit" disabled={!isDirty || isLoading}>
            {isLoading ? (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            ) : (
              <Save className="h-4 w-4" aria-hidden="true" />
            )}
            Save Changes
          </Button>
          {isDirty && (
            <span className="text-xs text-muted-foreground">
              Unsaved changes
            </span>
          )}
        </div>
      </form>

      {/* X-Change-Reason dialog */}
      {showReasonDialog && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center"
          aria-hidden={!showReasonDialog}
        >
          <div
            className="fixed inset-0 bg-black/50"
            aria-hidden="true"
            onClick={() => setShowReasonDialog(false)}
          />
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="change-reason-title"
            className="relative z-10 w-full max-w-md rounded-lg bg-background p-6 shadow-xl"
          >
            <h2
              id="change-reason-title"
              className="text-lg font-semibold text-foreground"
            >
              Reason for Change
            </h2>
            <p className="mt-2 text-sm text-muted-foreground">
              Provide a reason for this configuration change. This will be
              recorded in the audit trail.
            </p>
            <div className="mt-4">
              <label
                htmlFor="change-reason-input"
                className="block text-sm font-medium text-foreground"
              >
                Change Reason
              </label>
              <textarea
                id="change-reason-input"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Describe why this configuration is being changed..."
                rows={3}
                maxLength={500}
                className="mt-1 block w-full rounded-md border border-border bg-background px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                autoFocus
              />
              <p className="mt-1 text-xs text-muted-foreground">
                {reason.trim().length}/500 characters
              </p>
            </div>
            <div className="mt-6 flex justify-end gap-3">
              <Button
                variant="outline"
                onClick={() => {
                  setShowReasonDialog(false);
                  setReason("");
                }}
              >
                Cancel
              </Button>
              <Button
                disabled={reason.trim().length < 1}
                onClick={() => handleSubmit((data) => handleConfirmSubmit(data))()}
              >
                Confirm
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
