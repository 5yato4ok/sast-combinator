import { getCurrentCustomization } from '@/lib/config/domain-config';

function loadBrandConfig() {
  const customization = getCurrentCustomization();

  try {
    const jsonConfig = require(`../public/config/${customization}.json`);
    return jsonConfig;
  } catch (error) {
    console.warn(`Failed to load customization config for '${customization}', using fallback`, error);
    return {};
  }
}

export const config = loadBrandConfig();
