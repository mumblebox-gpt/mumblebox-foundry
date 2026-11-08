// One activity policy for destructive maintenance and update actions.
export const maintenanceBusy=status=>!status||status.maintenance_active||status.running||status.download?.status==='running'||status.resource_download?.status==='running'||status.resource_cleanup?.status==='releasing';
