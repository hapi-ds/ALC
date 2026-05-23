import { Image, FileText, Volume2 } from "lucide-react";
import type { VideoStepInfo } from "@/types/videoAlignment";

/**
 * Props for the VideoStepDetail component.
 */
export interface VideoStepDetailProps {
  /** The video step information to display */
  step: VideoStepInfo;
  /** Callback to close the detail view */
  onClose?: () => void;
}

/**
 * Format seconds to MM:SS display string.
 */
function formatTimestamp(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, "0")}`;
}

/**
 * VideoStepDetail displays detailed information about a selected video step.
 *
 * Shows:
 * - Frame thumbnails for the step's timestamp range (placeholder images if unavailable)
 * - Full description text
 * - Audio transcript text (if available)
 *
 * Validates: Requirements 11.4
 */
export function VideoStepDetail({ step, onClose }: VideoStepDetailProps) {
  const hasFrames = step.frame_thumbnails.length > 0;
  const hasTranscript = step.audio_transcript != null && step.audio_transcript.trim().length > 0;

  return (
    <div
      className="border border-border rounded-lg p-4 space-y-4 bg-card"
      aria-label="Video step detail"
    >
      {/* Header with timestamp range and close button */}
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-semibold text-foreground">
          Step Detail ({formatTimestamp(step.timestamp_start)} – {formatTimestamp(step.timestamp_end)})
        </h4>
        {onClose && (
          <button
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground text-sm px-2 py-1 rounded hover:bg-muted transition-colors"
            aria-label="Close step detail"
          >
            ✕
          </button>
        )}
      </div>

      {/* Frame thumbnails */}
      <div className="space-y-2">
        <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
          <Image className="h-3.5 w-3.5" aria-hidden="true" />
          <span>Frame Thumbnails</span>
        </div>
        {hasFrames ? (
          <div className="flex gap-2 overflow-x-auto pb-2" role="list" aria-label="Frame thumbnails">
            {step.frame_thumbnails.map((src, idx) => (
              <img
                key={idx}
                src={src}
                alt={`Frame ${idx + 1} at ${formatTimestamp(step.timestamp_start)}`}
                className="h-20 w-auto rounded border border-border object-cover shrink-0"
              />
            ))}
          </div>
        ) : (
          <div
            className="flex items-center justify-center h-20 rounded border border-dashed border-border bg-muted/30 text-xs text-muted-foreground"
            aria-label="No frame thumbnails available"
          >
            <span>No frame thumbnails available</span>
          </div>
        )}
      </div>

      {/* Full description */}
      <div className="space-y-1.5">
        <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
          <FileText className="h-3.5 w-3.5" aria-hidden="true" />
          <span>Description</span>
        </div>
        <p className="text-sm text-foreground leading-relaxed">{step.description}</p>
      </div>

      {/* Audio transcript */}
      <div className="space-y-1.5">
        <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
          <Volume2 className="h-3.5 w-3.5" aria-hidden="true" />
          <span>Audio Transcript</span>
        </div>
        {hasTranscript ? (
          <p className="text-sm text-foreground leading-relaxed italic bg-muted/30 rounded p-2">
            {step.audio_transcript}
          </p>
        ) : (
          <p className="text-xs text-muted-foreground italic">
            No audio transcript available for this step.
          </p>
        )}
      </div>
    </div>
  );
}
