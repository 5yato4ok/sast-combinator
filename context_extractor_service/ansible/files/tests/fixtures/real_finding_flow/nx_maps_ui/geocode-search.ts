import { logger } from '@/lib/logging/default-logger';

export const geocodeSearch = async () => {
    try {
        return [{ bbox: [], geometry: { coordinates: [0, 0] }, properties: { feature_type: 'place' } }].map((feature) => {
            const secondaryText = '';
            return {
                secondaryText,
                type: feature.properties.feature_type,
                center: feature.geometry.coordinates,
                bbox: feature.bbox,
                context: feature.properties.context || {},
                properties: feature.properties
            };
        });
    } catch (error) {
        logger.error('Geocoding error:', error);
        return [];
    }
};
