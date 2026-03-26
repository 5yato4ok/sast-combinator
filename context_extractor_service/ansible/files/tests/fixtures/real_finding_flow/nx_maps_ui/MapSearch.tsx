import { logger } from '@/lib/logging/default-logger';

export const MapSearch = ({ map, setSelectedMarker }) => {
    const handleSelectionChange = (event, selectedOption) => {
        if (!selectedOption) {
            setSelectedMarker({ selectedMarker: null });
            return;
        }

        if (event?.type === 'click' || event?.type === 'keydown') {
            if (selectedOption.isLocal) {
                searchValueNow(selectedOption.name);
            } else {
                const { center } = selectedOption;
                if (!center || !Array.isArray(center) || center.length !== 2) {
                    logger.error('Invalid coordinates for geocoding result:', selectedOption);
                    return;
                }
            }
        }
    };

    const searchValueNow = (value) => {
        let targetSearch = findClosestMatchMarker([], value);
        if (targetSearch) {
            logger.debug(`Flying to ${targetSearch?.type}`);
        }
        if (targetSearch?.nxmaps) {
            try {
                const nxmapsData = JSON.parse(targetSearch.nxmaps);
                if (nxmapsData?.location) {
                    map.flyTo({ center: nxmapsData.location[0].center });
                }
            } catch (e) {
                logger.error('Error parsing nxmaps data:', e);
            }
        }
    };

    return (
        <button onClick={(event) => handleSelectionChange(event, { isLocal: true, name: 'x' })}>
            Search
        </button>
    );
};
