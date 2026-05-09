import { useRef, useEffect, useCallback } from 'react';
import BpmnModeler from 'bpmn-js/lib/Modeler';
import BpmnViewer from 'bpmn-js/lib/Viewer';
import 'bpmn-js/dist/assets/bpmn-js.css';
import 'bpmn-js/dist/assets/diagram-js.css';
import 'bpmn-js/dist/assets/bpmn-font/css/bpmn-embedded.css';

import customPaletteModule from './customPalette';
import alcoaExtension from './alcoaExtension.json';

/**
 * Props for the BpmnEditor component.
 */
export interface BpmnEditorProps {
  /** Initial BPMN XML to render (empty string for new canvas) */
  initialXml: string;
  /** Called on every canvas change with updated XML */
  onXmlChange: (xml: string) => void;
  /** Called when transitions change (extracted from sequence flows) */
  onTransitionsChange: (transitions: string[]) => void;
  /** Whether the editor is read-only (for version preview) */
  readOnly?: boolean;
}

/** Unicode arrow character for transition strings */
const ARROW = '\u2192';

/**
 * Default empty BPMN diagram with a single start event.
 */
const DEFAULT_BPMN_XML = `<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                  xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI"
                  xmlns:dc="http://www.omg.org/spec/DD/20100524/DC"
                  id="Definitions_1"
                  targetNamespace="http://bpmn.io/schema/bpmn">
  <bpmn:process id="Process_1" isExecutable="false">
    <bpmn:startEvent id="StartEvent_1" name="Start" />
  </bpmn:process>
  <bpmndi:BPMNDiagram id="BPMNDiagram_1">
    <bpmndi:BPMNPlane id="BPMNPlane_1" bpmnElement="Process_1">
      <bpmndi:BPMNShape id="StartEvent_1_di" bpmnElement="StartEvent_1">
        <dc:Bounds x="180" y="160" width="36" height="36" />
      </bpmndi:BPMNShape>
    </bpmndi:BPMNPlane>
  </bpmndi:BPMNDiagram>
</bpmn:definitions>`;

/**
 * Extract transition strings from the element registry of a bpmn-js instance.
 * Transitions are formatted as "SourceTaskName→TargetTaskName" for sequence
 * flows connecting two Task elements.
 */
function extractTransitions(modeler: BpmnModeler | BpmnViewer): string[] {
  try {
    const elementRegistry = modeler.get<{ getAll(): Array<{ type: string; businessObject: Record<string, unknown> }> }>('elementRegistry');
    const elements = elementRegistry.getAll();
    const transitions: string[] = [];

    for (const element of elements) {
      if (element.type === 'bpmn:SequenceFlow') {
        const bo = element.businessObject as {
          sourceRef?: { $type?: string; name?: string };
          targetRef?: { $type?: string; name?: string };
        };

        const source = bo.sourceRef;
        const target = bo.targetRef;

        // Only extract transitions between Task elements
        if (
          source &&
          target &&
          source.$type === 'bpmn:Task' &&
          target.$type === 'bpmn:Task'
        ) {
          const sourceName = source.name || 'Unnamed Task';
          const targetName = target.name || 'Unnamed Task';
          transitions.push(`${sourceName}${ARROW}${targetName}`);
        }
      }
    }

    return transitions;
  } catch {
    return [];
  }
}

/**
 * BPMN visual editor component wrapping bpmn-js.
 *
 * Mounts a bpmn-js Modeler (or Viewer if readOnly) on a container div,
 * configures the restricted palette and alcoa moddle extension, and
 * emits XML and transition changes on every diagram modification.
 */
export function BpmnEditor({
  initialXml,
  onXmlChange,
  onTransitionsChange,
  readOnly = false,
}: BpmnEditorProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const modelerRef = useRef<BpmnModeler | BpmnViewer | null>(null);
  const isImportingRef = useRef(false);

  /**
   * Handle diagram changes: export XML and extract transitions.
   */
  const handleChange = useCallback(async () => {
    if (isImportingRef.current) return;
    const instance = modelerRef.current;
    if (!instance) return;

    try {
      const { xml } = await instance.saveXML({ format: true });
      if (xml) {
        onXmlChange(xml);
      }
      const transitions = extractTransitions(instance);
      onTransitionsChange(transitions);
    } catch {
      // saveXML can fail if the diagram is in an invalid state during editing
    }
  }, [onXmlChange, onTransitionsChange]);

  /**
   * Initialize the bpmn-js instance and import the initial XML.
   */
  useEffect(() => {
    if (!containerRef.current) return;

    let instance: BpmnModeler | BpmnViewer;

    if (readOnly) {
      instance = new BpmnViewer({
        container: containerRef.current,
        moddleExtensions: {
          alcoa: alcoaExtension,
        },
      });
    } else {
      instance = new BpmnModeler({
        container: containerRef.current,
        additionalModules: [customPaletteModule],
        moddleExtensions: {
          alcoa: alcoaExtension,
        },
      });

      // Register change listener on the command stack
      instance.on('commandStack.changed', () => {
        void handleChange();
      });
    }

    modelerRef.current = instance;

    // Import initial XML
    const xmlToImport = initialXml || DEFAULT_BPMN_XML;
    isImportingRef.current = true;
    instance.importXML(xmlToImport).then(() => {
      isImportingRef.current = false;
      // Extract initial transitions after import
      const transitions = extractTransitions(instance);
      onTransitionsChange(transitions);
    }).catch(() => {
      isImportingRef.current = false;
    });

    return () => {
      instance.destroy();
      modelerRef.current = null;
    };
    // Only run on mount/unmount and when readOnly changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [readOnly]);

  /**
   * Re-import XML when initialXml prop changes (e.g., loading a version).
   * Skip if the instance hasn't been created yet (handled by mount effect).
   */
  useEffect(() => {
    const instance = modelerRef.current;
    if (!instance) return;

    const xmlToImport = initialXml || DEFAULT_BPMN_XML;
    isImportingRef.current = true;
    instance.importXML(xmlToImport).then(() => {
      isImportingRef.current = false;
      const transitions = extractTransitions(instance);
      onTransitionsChange(transitions);
    }).catch(() => {
      isImportingRef.current = false;
    });
    // Only re-import when initialXml changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialXml]);

  /**
   * Zoom in on the canvas.
   */
  const handleZoomIn = useCallback(() => {
    const instance = modelerRef.current;
    if (!instance) return;
    try {
      const canvas = instance.get<{ zoom(level: string | number): void; zoom(): number }>('canvas');
      const currentZoom = canvas.zoom();
      canvas.zoom(currentZoom * 1.2);
    } catch {
      // Canvas may not be available
    }
  }, []);

  /**
   * Zoom out on the canvas.
   */
  const handleZoomOut = useCallback(() => {
    const instance = modelerRef.current;
    if (!instance) return;
    try {
      const canvas = instance.get<{ zoom(level: string | number): void; zoom(): number }>('canvas');
      const currentZoom = canvas.zoom();
      canvas.zoom(currentZoom / 1.2);
    } catch {
      // Canvas may not be available
    }
  }, []);

  /**
   * Fit the diagram to the viewport.
   */
  const handleFitViewport = useCallback(() => {
    const instance = modelerRef.current;
    if (!instance) return;
    try {
      const canvas = instance.get<{ zoom(level: string): void }>('canvas');
      canvas.zoom('fit-viewport');
    } catch {
      // Canvas may not be available
    }
  }, []);

  return (
    <div className="relative flex flex-col h-full w-full">
      {/* Zoom controls */}
      <div className="absolute top-2 right-2 z-10 flex gap-1">
        <button
          type="button"
          onClick={handleZoomIn}
          className="rounded bg-white border border-gray-300 px-2 py-1 text-sm shadow-sm hover:bg-gray-50"
          aria-label="Zoom in"
          title="Zoom in"
        >
          +
        </button>
        <button
          type="button"
          onClick={handleZoomOut}
          className="rounded bg-white border border-gray-300 px-2 py-1 text-sm shadow-sm hover:bg-gray-50"
          aria-label="Zoom out"
          title="Zoom out"
        >
          −
        </button>
        <button
          type="button"
          onClick={handleFitViewport}
          className="rounded bg-white border border-gray-300 px-2 py-1 text-sm shadow-sm hover:bg-gray-50"
          aria-label="Fit to viewport"
          title="Fit to viewport"
        >
          ⊡
        </button>
      </div>

      {/* BPMN canvas container */}
      <div
        ref={containerRef}
        className="flex-1 min-h-[400px] w-full"
        role="application"
        aria-label="BPMN workflow diagram editor"
      />
    </div>
  );
}
