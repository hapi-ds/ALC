/**
 * Restricted palette provider for the BPMN workflow editor.
 *
 * Limits the palette to only the elements supported by the AlcoaBase
 * workflow engine: Start Event, End Event, Task, and connection/layout tools.
 *
 * @see https://github.com/bpmn-io/bpmn-js-examples/tree/main/custom-elements
 */

type PaletteEntry = {
  group: string;
  className: string;
  title: string;
  separator?: boolean;
  action?: {
    dragstart?: (event: Event) => void;
    click?: (event: Event) => void;
  };
};

type PaletteEntries = Record<string, PaletteEntry>;

interface Palette {
  registerProvider(provider: unknown): void;
}

interface Create {
  start(event: Event, shape: unknown): void;
}

interface ElementFactory {
  createShape(attrs: { type: string }): unknown;
}

interface SpaceTool {
  activateSelection(event: Event): void;
}

interface LassoTool {
  activateSelection(event: Event): void;
}

interface GlobalConnect {
  start(event: Event): void;
}

interface Translate {
  (template: string, replacements?: Record<string, string>): string;
}

/**
 * A restricted palette provider that only exposes elements supported
 * by the AlcoaBase workflow engine backend parser:
 * - Start Event
 * - End Event
 * - Task (workflow state)
 * - Sequence Flow (via global connect tool)
 * - Space tool
 * - Lasso tool
 */
class RestrictedPaletteProvider {
  static $inject = [
    'palette',
    'create',
    'elementFactory',
    'spaceTool',
    'lassoTool',
    'globalConnect',
    'translate',
  ];

  private _create: Create;
  private _elementFactory: ElementFactory;
  private _spaceTool: SpaceTool;
  private _lassoTool: LassoTool;
  private _globalConnect: GlobalConnect;
  private _translate: Translate;

  constructor(
    palette: Palette,
    create: Create,
    elementFactory: ElementFactory,
    spaceTool: SpaceTool,
    lassoTool: LassoTool,
    globalConnect: GlobalConnect,
    translate: Translate,
  ) {
    this._create = create;
    this._elementFactory = elementFactory;
    this._spaceTool = spaceTool;
    this._lassoTool = lassoTool;
    this._globalConnect = globalConnect;
    this._translate = translate;

    palette.registerProvider(this);
  }

  getPaletteEntries(): PaletteEntries {
    const create = this._create;
    const elementFactory = this._elementFactory;
    const spaceTool = this._spaceTool;
    const lassoTool = this._lassoTool;
    const globalConnect = this._globalConnect;
    const translate = this._translate;

    function createAction(
      type: string,
      group: string,
      className: string,
      title: string,
    ): PaletteEntry {
      function createListener(event: Event) {
        const shape = elementFactory.createShape({ type });
        create.start(event, shape);
      }

      return {
        group,
        className,
        title,
        action: {
          dragstart: createListener,
          click: createListener,
        },
      };
    }

    return {
      'lasso-tool': {
        group: 'tools',
        className: 'bpmn-icon-lasso-tool',
        title: translate('Activate lasso tool'),
        action: {
          click(event: Event) {
            lassoTool.activateSelection(event);
          },
        },
      },
      'space-tool': {
        group: 'tools',
        className: 'bpmn-icon-space-tool',
        title: translate('Activate create/remove space tool'),
        action: {
          click(event: Event) {
            spaceTool.activateSelection(event);
          },
        },
      },
      'global-connect-tool': {
        group: 'tools',
        className: 'bpmn-icon-connection-multi',
        title: translate('Activate global connect tool'),
        action: {
          click(event: Event) {
            globalConnect.start(event);
          },
        },
      },
      'tool-separator': {
        group: 'tools',
        separator: true,
        className: '',
        title: '',
      },
      'create.start-event': createAction(
        'bpmn:StartEvent',
        'event',
        'bpmn-icon-start-event-none',
        translate('Create start event'),
      ),
      'create.end-event': createAction(
        'bpmn:EndEvent',
        'event',
        'bpmn-icon-end-event-none',
        translate('Create end event'),
      ),
      'create.task': createAction(
        'bpmn:Task',
        'activity',
        'bpmn-icon-task',
        translate('Create task'),
      ),
    };
  }
}

/**
 * bpmn-js additional module definition.
 * Replaces the default PaletteProvider with our restricted version.
 */
export default {
  __init__: ['restrictedPaletteProvider'],
  restrictedPaletteProvider: ['type', RestrictedPaletteProvider],
};
