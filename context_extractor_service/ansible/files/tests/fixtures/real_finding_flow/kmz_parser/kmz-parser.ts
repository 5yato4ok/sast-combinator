import JSZip from 'jszip';
import { logger } from '@/lib/logging/default-logger';
import type { GeoJSONData, GeoJSONFeature } from '@/types/map';

export async function extractIcons(zipFile: JSZip): Promise<Record<string, string>> {
  const icons: Record<string, string> = {};

  const imageFiles = Object.keys(zipFile.files).filter(name =>
    name.toLowerCase().match(/\.(png|jpg|jpeg|gif)$/i)
  );

  logger.debug(`[KMZ] Found ${imageFiles.length} image files in KMZ:`, imageFiles);

  for (const filename of imageFiles) {
    try {
      const fileData = await zipFile.files[filename].async('base64');
      const ext = filename.toLowerCase().split('.').pop();
      icons[filename] = `data:image/png;base64,${fileData}`;
    } catch (error) {
      logger.warn(`[KMZ] Failed to extract icon ${filename}:`, error);
    }
  }

  return icons;
}
