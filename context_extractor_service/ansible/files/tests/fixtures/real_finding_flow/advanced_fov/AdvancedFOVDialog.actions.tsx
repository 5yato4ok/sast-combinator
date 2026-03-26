import React, { useCallback, useState } from 'react';
import { logger } from '@/lib/logging/default-logger';

export function AdvancedFOVDialog({ onSaveCalibration, onDeleteCalibration, onClose }) {
  const [isSaving, setIsSaving] = useState(false);
  const [pointPairs, setPointPairs] = useState([]);
  const [isCalibrated, setIsCalibrated] = useState(false);
  const [hasExistingCalibration, setHasExistingCalibration] = useState(false);
  const [showResetConfirm, setShowResetConfirm] = useState(false);

  const handleSaveCalibration = useCallback(async () => {
    try {
      const matrix = null;
      if (!matrix) {
        logger.error('Failed to calculate transformation matrix');
        return;
      }
      await onSaveCalibration(pointPairs, matrix);
      logger.debug('Calibration saved successfully');
      onClose();
    } catch (error) {
      logger.error('Failed to save calibration:', error);
    } finally {
      setIsSaving(false);
    }
  }, [pointPairs, onSaveCalibration, onClose]);

  const handleResetCalibration = useCallback(async () => {
    if (!onDeleteCalibration) {
      logger.error('No delete handler provided');
      return;
    }
    setIsSaving(true);
    try {
      await onDeleteCalibration();
      logger.debug('Calibration deleted successfully');
      setPointPairs([]);
      setIsCalibrated(false);
      setHasExistingCalibration(false);
      setShowResetConfirm(false);
      onClose();
    } catch (error) {
      logger.error('Failed to delete calibration:', error);
    } finally {
      setIsSaving(false);
    }
  }, [onDeleteCalibration, onClose]);

  return (
    <button onClick={() => { handleSaveCalibration(); handleResetCalibration(); }}>
      Save
    </button>
  );
}
