import React, { useCallback, useState, useRef } from 'react';
import { Box, Dialog, Typography } from '@mui/material';
import Image from 'next/image';
import { logger } from '@/lib/logging/default-logger';

export function AdvancedFOVDialog({
  show,
  thumbnail,
}) {
  const transformPoint = useCallback((result: { lng: number; lat: number }) => {
    try {
      if (result.lng > 1) {
        return {
          x: result.lng,
          y: result.lat,
        };
      }
      return {
        x: result.lng,
        y: result.lat,
      };
    } catch (error) {
      logger.error('Failed to transform point:', error);
      return { x: 0, y: 0 };
    }
  }, []);
}
