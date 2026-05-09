/**
 * Local type declarations for bpmn-js subpath imports.
 *
 * bpmn-js ships its own .d.ts files (lib/Modeler.d.ts, lib/Viewer.d.ts),
 * but this file provides supplementary declarations for internal modules
 * and custom extension types used in the workflow editor.
 */

declare module 'bpmn-js/lib/Modeler' {
  import Modeler from 'bpmn-js/lib/Modeler';
  export default Modeler;
}

declare module 'bpmn-js/lib/Viewer' {
  import Viewer from 'bpmn-js/lib/Viewer';
  export default Viewer;
}

declare module 'bpmn-js/lib/NavigatedViewer' {
  import NavigatedViewer from 'bpmn-js/lib/NavigatedViewer';
  export default NavigatedViewer;
}
