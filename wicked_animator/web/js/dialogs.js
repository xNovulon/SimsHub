// Dialogs: send to game, open project, add sound, import an animation as keys, name, Tray sims.
// Each lives in dialogs/ (one file each); this file keeps the old names, so every existing import still works.
export { openNameDialog, ensureNamed } from './dialogs/name.js';
export { WW_LOCATIONS, openExportDialog } from './dialogs/export.js';
export { openTrayDialog } from './dialogs/tray.js';
export { openProjectDialog } from './dialogs/project.js';
export { openAddSoundDialog } from './dialogs/sound.js';
export { openImportDialog } from './dialogs/import.js';
