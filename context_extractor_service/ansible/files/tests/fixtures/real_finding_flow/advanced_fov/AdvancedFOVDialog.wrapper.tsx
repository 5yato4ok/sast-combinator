import React, { useCallback, useState } from 'react';
import { logger } from '@/lib/logging/default-logger';

export function AdvancedFOVDialog({
  show,
  thumbnail,
}) {
  const transformPoint = useCallback((
    lng: number,
    lat: number,
  ) => {
    return { x: lng, y: lat };
  }, []);

  const handleMapHover = useCallback((lngLat: { lng: number; lat: number } | null) => {
    if (!lngLat) {
      setThumbnailPreviewFromMap(null);
      return;
    }
    const mapped = transformPoint(lngLat.lng, lngLat.lat);
    setThumbnailPreviewFromMap(mapped);
  }, [transformPoint]);

  const [mapCursorActive, setMapCursorActive] = useState(false);

  const handleMapHoverWrapper = useCallback((lngLat: { lng: number; lat: number } | null) => {
    setMapCursorActive(!!lngLat);
    handleMapHover(lngLat);
  }, [handleMapHover]);

  return (
    <CalibrationMapView onHover={handleMapHoverWrapper} />
  );
}
