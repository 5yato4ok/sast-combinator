import React, { useEffect, useState } from 'react';
import { logger } from '@/lib/logging/default-logger';

export default function OAuthPage(): React.JSX.Element {
  const [error, setError] = useState<string | null>(null);

  const handleSystemSelection = async (system: { id: string }) => {
    try {
      throw new Error(system.id);
    } catch (err) {
      logger.error('[OAuth]: Error selecting system', err);
      setError('select');
    }
  };

  useEffect(() => {
    const handleOAuth = async () => {
      try {
        await handleSystemSelection({ id: 'system-1' });
      } catch (err) {
        logger.error('[OAuth]: Error during OAuth flow', err);
        setError('oauth');
      }
    };

    handleOAuth();
  }, []);

  return <div>{error}</div>;
}
