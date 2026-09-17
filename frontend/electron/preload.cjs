const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  isElectron: true,
  runPipeline: (config) => ipcRenderer.invoke('run-pipeline', config),
  stopPipeline: () => ipcRenderer.invoke('stop-pipeline'),
  onPipelineLog: (callback) => {
    const handler = (_event, data) => callback(data);
    ipcRenderer.on('pipeline-log', handler);
    return () => ipcRenderer.removeListener('pipeline-log', handler);
  },
  onPipelineExit: (callback) => {
    const handler = (_event, code) => callback(code);
    ipcRenderer.on('pipeline-exit', handler);
    return () => ipcRenderer.removeListener('pipeline-exit', handler);
  },
  listProjects: () => ipcRenderer.invoke('list-projects'),
  getProjectDetails: (projectName) => ipcRenderer.invoke('get-project-details', projectName),
  openPath: (folderOrFilePath) => ipcRenderer.invoke('open-path', folderOrFilePath),
  selectFile: (options) => ipcRenderer.invoke('select-file', options),
  getSystemStatus: () => ipcRenderer.invoke('get-system-status'),
  saveEnv: (envVars) => ipcRenderer.invoke('save-env', envVars),
});
