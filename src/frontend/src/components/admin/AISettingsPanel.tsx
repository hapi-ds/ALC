import { useEffect, useState } from "react";
import { Cpu, Zap, TestTube, RefreshCw, CheckCircle2, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/apiClient";

interface AIHardwareConfig {
  model_chat_name: string;
  model_chat_path: string;
  model_chat_max_gpu_memory_gb: number;
  model_embedding_name: string;
  model_embedding_path: string;
  model_embedding_dimension: number;
  model_ocr_name: string;
  model_ocr_path: string;
  inference_mode: "gpu" | "cpu" | "mock";
  gpu_device_id: number;
  vllm_chat_url: string;
  vllm_embedding_url: string;
  vllm_chat_status: string;
  vllm_embedding_status: string;
  restart_required?: boolean;
}

const MODE_LABELS: Record<string, { label: string; icon: typeof Cpu; color: string }> = {
  gpu: { label: "GPU", icon: Zap, color: "text-green-600" },
  cpu: { label: "CPU", icon: Cpu, color: "text-yellow-600" },
  mock: { label: "Mock (Development)", icon: TestTube, color: "text-blue-600" },
};

export function AISettingsPanel() {
  const [config, setConfig] = useState<AIHardwareConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [switching, setSwitching] = useState(false);

  const fetchConfig = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiClient.get<AIHardwareConfig>("/api/system-config/ai-hardware");
      setConfig(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load AI configuration");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchConfig();
  }, []);

  const switchMode = async (mode: "gpu" | "cpu" | "mock") => {
    setSwitching(true);
    try {
      const data = await apiClient.put<AIHardwareConfig>(
        "/api/system-config/ai-hardware",
        { inference_mode: mode },
        { changeReason: `Switch AI mode to ${mode}` },
      );
      setConfig(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to switch mode");
    } finally {
      setSwitching(false);
    }
  };

  if (loading) {
    return (
      <div className="rounded-lg border border-border p-6 animate-pulse">
        <div className="h-6 w-48 bg-muted rounded mb-4" />
        <div className="space-y-3">
          <div className="h-4 w-full bg-muted rounded" />
          <div className="h-4 w-3/4 bg-muted rounded" />
        </div>
      </div>
    );
  }

  if (error && !config) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-6">
        <p className="text-sm text-red-800">{error}</p>
        <Button variant="outline" size="sm" className="mt-3" onClick={fetchConfig}>
          Retry
        </Button>
      </div>
    );
  }

  if (!config) return null;

  const modeInfo = MODE_LABELS[config.inference_mode] ?? MODE_LABELS.mock;
  const ModeIcon = modeInfo.icon;

  return (
    <div className="space-y-6">
      {/* Current Mode */}
      <div className="rounded-lg border border-border p-6">
        <h3 className="text-lg font-semibold mb-4">Inference Mode</h3>
        <div className="flex items-center gap-3 mb-4">
          <ModeIcon className={`h-6 w-6 ${modeInfo.color}`} />
          <span className="text-lg font-medium">{modeInfo.label}</span>
        </div>
        <div className="flex gap-2">
          {(["gpu", "cpu", "mock"] as const).map((mode) => {
            const info = MODE_LABELS[mode];
            const Icon = info.icon;
            return (
              <Button
                key={mode}
                variant={config.inference_mode === mode ? "default" : "outline"}
                size="sm"
                disabled={switching || config.inference_mode === mode}
                onClick={() => switchMode(mode)}
              >
                <Icon className="h-4 w-4 mr-1" />
                {info.label}
              </Button>
            );
          })}
        </div>
      </div>

      {/* vLLM Status */}
      <div className="rounded-lg border border-border p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold">vLLM Service Status</h3>
          <Button variant="ghost" size="sm" onClick={fetchConfig}>
            <RefreshCw className="h-4 w-4 mr-1" />
            Refresh
          </Button>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <StatusCard label="Chat Model" status={config.vllm_chat_status} url={config.vllm_chat_url} />
          <StatusCard label="Embedding Model" status={config.vllm_embedding_status} url={config.vllm_embedding_url} />
        </div>
      </div>

      {/* Model Configuration */}
      <div className="rounded-lg border border-border p-6">
        <h3 className="text-lg font-semibold mb-4">Model Configuration</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
          <ConfigRow label="Chat Model" value={config.model_chat_name} />
          <ConfigRow label="Chat Path" value={config.model_chat_path} />
          <ConfigRow label="Embedding Model" value={config.model_embedding_name} />
          <ConfigRow label="Embedding Dimension" value={String(config.model_embedding_dimension)} />
          <ConfigRow label="OCR Model" value={config.model_ocr_name} />
          <ConfigRow label="GPU Device" value={`cuda:${config.gpu_device_id}`} />
          <ConfigRow label="Max GPU Memory" value={`${config.model_chat_max_gpu_memory_gb} GB`} />
        </div>
      </div>
    </div>
  );
}

function StatusCard({ label, status, url }: { label: string; status: string; url: string }) {
  const isHealthy = status === "reachable" || status === "running" || status === "healthy";
  return (
    <div className={`rounded-md border p-4 ${isHealthy ? "border-green-200 bg-green-50/30" : "border-red-200 bg-red-50/30"}`}>
      <div className="flex items-center gap-2 mb-2">
        {isHealthy ? (
          <CheckCircle2 className="h-4 w-4 text-green-500" />
        ) : (
          <XCircle className="h-4 w-4 text-red-500" />
        )}
        <span className="font-medium text-sm">{label}</span>
      </div>
      <p className="text-xs text-muted-foreground">Status: {status}</p>
      {url && <p className="text-xs text-muted-foreground">URL: {url}</p>}
    </div>
  );
}

function ConfigRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span className="text-muted-foreground">{label}:</span>{" "}
      <span className="font-medium text-foreground">{value || "—"}</span>
    </div>
  );
}
