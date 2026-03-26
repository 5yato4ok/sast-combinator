import React, { useEffect, useRef } from 'react';
import { usePathname } from 'next/navigation';
import { logger } from '@/lib/logging/default-logger';

export function AuthGuard(): React.JSX.Element | null {
  const pathname = usePathname();
  const hasTriedOAuth = useRef(false);

  const handleOAuthLogin = async (): Promise<void> => {
    return;
  };

  useEffect(() => {
    if (!hasTriedOAuth.current) {
      hasTriedOAuth.current = true;
      handleOAuthLogin().catch((error) => {
        logger.error('[Auth]: OAuth login failed on navigation', error);
      });
    }
  }, [pathname]);

  return null;
}
