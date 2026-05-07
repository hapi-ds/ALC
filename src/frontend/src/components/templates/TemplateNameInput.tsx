import { useTemplateBuilderStore } from "../../stores/templateBuilderStore";

export function TemplateNameInput() {
  const templateName = useTemplateBuilderStore((s) => s.templateName);
  const nameError = useTemplateBuilderStore((s) => s.nameError);
  const setTemplateName = useTemplateBuilderStore((s) => s.setTemplateName);

  return (
    <div className="mb-4">
      <label
        htmlFor="template-name-input"
        className="block text-sm font-medium text-gray-700 mb-1"
      >
        Template Name
      </label>
      <input
        id="template-name-input"
        type="text"
        value={templateName}
        onChange={(e) => setTemplateName(e.target.value)}
        placeholder="Enter template name..."
        aria-describedby={nameError ? "template-name-error" : undefined}
        aria-invalid={!!nameError}
        className={`w-full rounded-md border px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 ${
          nameError
            ? "border-red-500 focus:ring-red-500"
            : "border-gray-300"
        }`}
      />
      {nameError && (
        <p
          id="template-name-error"
          className="mt-1 text-sm text-red-600"
          role="alert"
        >
          {nameError}
        </p>
      )}
    </div>
  );
}
