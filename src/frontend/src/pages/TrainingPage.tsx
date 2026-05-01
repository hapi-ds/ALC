import { GraduationCap, CheckCircle, Clock, BookOpen } from "lucide-react";

export function TrainingPage() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold">Training Dashboard</h2>
        <p className="text-sm text-muted-foreground">
          Track training tasks, completion status, and view training content
        </p>
      </div>

      {/* Stats overview */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="border border-border rounded-lg p-4">
          <div className="flex items-center gap-2 text-muted-foreground">
            <Clock className="h-4 w-4" aria-hidden="true" />
            <span className="text-sm">Pending</span>
          </div>
          <p className="text-2xl font-bold mt-1">0</p>
        </div>
        <div className="border border-border rounded-lg p-4">
          <div className="flex items-center gap-2 text-muted-foreground">
            <CheckCircle className="h-4 w-4" aria-hidden="true" />
            <span className="text-sm">Completed</span>
          </div>
          <p className="text-2xl font-bold mt-1">0</p>
        </div>
        <div className="border border-border rounded-lg p-4">
          <div className="flex items-center gap-2 text-muted-foreground">
            <GraduationCap className="h-4 w-4" aria-hidden="true" />
            <span className="text-sm">Total Tasks</span>
          </div>
          <p className="text-2xl font-bold mt-1">0</p>
        </div>
      </div>

      {/* Task list placeholder */}
      <section aria-label="Training tasks">
        <h3 className="text-lg font-semibold mb-3">Training Tasks</h3>
        <div className="border border-border rounded-lg p-8 text-center text-muted-foreground">
          <BookOpen className="h-8 w-8 mx-auto mb-2 opacity-50" aria-hidden="true" />
          <p>No training tasks assigned</p>
        </div>
      </section>

      {/* Training content viewer placeholder */}
      <section aria-label="Training content">
        <h3 className="text-lg font-semibold mb-3">Training Content</h3>
        <p className="text-sm text-muted-foreground">
          Select a training task to view its content, quiz, and key points
        </p>
      </section>
    </div>
  );
}
