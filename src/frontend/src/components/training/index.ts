/**
 * Training Management UI - Barrel Export
 *
 * Re-exports all training components, types, and utilities
 * for convenient imports throughout the application.
 */

// Components
export { TrainingStatusOverview } from "./TrainingStatusOverview";
export { TrainingTaskCard } from "./TrainingTaskCard";
export { TaskCompletionDialog } from "./TaskCompletionDialog";
export { TrainingTaskList } from "./TrainingTaskList";
export { TrainingContentViewer } from "./TrainingContentViewer";
export { TrainingRecordsPanel } from "./TrainingRecordsPanel";
export { AdminTrainingView } from "./AdminTrainingView";
export { TrainingGateGuard } from "./TrainingGateGuard";
export { TrainingStatusBanner } from "./TrainingStatusBanner";
export { QuizTakingUI } from "./QuizTakingUI";

// AI Training Ecosystem Components
export { TrainingSchedulePanel } from "./TrainingSchedulePanel";
export { SkillGapAlert } from "./SkillGapAlert";
export { TrainingMaterialViewer } from "./TrainingMaterialViewer";
export { VirtualAuditInterface } from "./VirtualAuditInterface";
export { DynamicFeedbackPanel } from "./DynamicFeedbackPanel";
export { JobMonitor } from "./JobMonitor";
export { GenerateActions } from "./GenerateActions";

// AI Training Ecosystem Types
export type { TrainingItem } from "./TrainingSchedulePanel";

// Types
export type {
  TrainingTask,
  TrainingStatus,
  TrainingContent,
  QuizQuestion,
  ProceduralStep,
  TaskFilter,
  TrainingStatistics,
  GateCache,
} from "./types";

// Utilities
export {
  computeStatistics,
  truncateTitle,
  filterTasks,
  sortTasks,
  validateInputLength,
  deriveContentId,
  shouldRenderSection,
  shuffleAnswerOptions,
  determineRecordValidity,
  sortRecords,
  groupRecordsBySop,
  deriveUniqueSopPairs,
  shouldEnforceGate,
  checkGateFromTasks,
  buildGateCacheKey,
  invalidateGateCacheEntry,
  extractErrorMessage,
  formatAriaLabel,
} from "./utils";

// Utility types
export type { TrainingRecord, SopVersionPair, RecordSortKey } from "./utils";
