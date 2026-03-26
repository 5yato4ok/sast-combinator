import React from 'react';
import { logger } from '@/lib/logging/default-logger';

export const MapSearch = ({ map }) => {
  const searchValueNow = (value) => {
    let finalLocation;
    const targetSearch = { name: value };
    const [lng, lat] = ['bad', NaN];

    if (typeof lng !== 'number' || typeof lat !== 'number' || isNaN(lng) || isNaN(lat)) {
      logger.error('Invalid coordinate values:', { lng, lat });
      return;
    }

    if (finalLocation) {
      map.flyTo({ center: finalLocation });
    } else {
      logger.error('No valid location found for target:', targetSearch);
    }
  };

  const handleSelectionChange = () => {
    searchValueNow('alpha');
  };

  return <button onClick={handleSelectionChange}>Search</button>;
};
