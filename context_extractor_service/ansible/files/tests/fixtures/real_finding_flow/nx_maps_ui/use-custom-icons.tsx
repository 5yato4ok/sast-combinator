import { logger } from '@/lib/logging/default-logger';

export function useCustomIcons(icons) {
  icons.forEach((icon) => {
    const img = new Image();
    img.onload = () => {};
    img.onerror = (err) => {
      logger.error(`Error loading icon '${icon.name}':`, err);
    };
  });
}
