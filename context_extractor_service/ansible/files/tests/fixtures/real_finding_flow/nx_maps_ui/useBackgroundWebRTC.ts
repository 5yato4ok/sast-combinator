import { logger } from '@/lib/logging/default-logger';

export const useBackgroundWebRTC = () => {
  const clientsRef = { current: new Map<string, { disconnect: () => Promise<void> }>() };

  const disconnectAll = async () => {
    logger.debug('[BackgroundWebRTC] Disconnecting all clients');
    const clients = Array.from(clientsRef.current.values());

    await Promise.all(
      clients.map(async (client) => {
        try {
          await client.disconnect();
        } catch (err) {
          logger.error('[BackgroundWebRTC] Error disconnecting client:', err);
        }
      })
    );

    clientsRef.current.clear();
  };

  return { disconnectAll };
};
