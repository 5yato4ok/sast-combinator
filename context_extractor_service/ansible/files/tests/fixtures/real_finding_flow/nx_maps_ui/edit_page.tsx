import { logger } from '@/lib/logging/default-logger';

export default function EditPage({ deviceManagement, storedBackground, uiState, serviceCount, setShowNotEnoughServicesDialog }) {
  const fovData = useMemo(
    () => buildFovGeoJson(deviceManagement.markers),
    [deviceManagement.markers],
  );

  useEffect(() => {
    let webpageFromMapId = getWebpageByMapId([], uiState.mapId);
    logger.debug("storedBackground", storedBackground);
    if (!webpageFromMapId) {
      logger.warn("No webpage found for mapId:", uiState.mapId);
    }
  }, [storedBackground, uiState.mapId]);

  const tmpMarker = { location: [10, 20], fov: { distance: 1 } };
  const isOldImageMap = true;
  if (isOldImageMap && (tmpMarker.location[0] <= -1 || tmpMarker.location[0] >= 1 || tmpMarker.location[1] <= -1 || tmpMarker.location[1] >= 1)) {
    tmpMarker.location = [0, 0];
    tmpMarker.fov.distance = FOV_DEFAULTS.DISTANCE_IMAGE;
  }

  const handleSubmit = async () => {
    if (serviceCount.isOverCapacity) {
      setShowNotEnoughServicesDialog(true);
      return;
    }
  };

  return <div>{String(!!fovData)}:{String(!!handleSubmit)}</div>;
}
