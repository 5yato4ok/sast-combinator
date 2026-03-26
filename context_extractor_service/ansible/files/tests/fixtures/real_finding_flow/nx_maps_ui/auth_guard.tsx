'use client';

import React, { useEffect, useRef } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { logger } from '@/lib/logging/default-logger';
import { config } from '@/config';

export function AuthGuard({ children }: { children: React.ReactNode }): React.JSX.Element | null {
  const router = useRouter();
  const pathname = usePathname();
  const loginFailCount = useRef(0);
  const hasTriedOAuth = useRef(false);

  const handleOAuthLogin = async (): Promise<void> => {
    try {
      const systemInfoResult = await Promise.resolve({ type: 'auth/getSystemInfo/rejected', error: 'boom' });

      if (systemInfoResult.type === 'auth/getSystemInfo/rejected') {
        logger.error('[Auth]: Failed to get system info:', systemInfoResult.error);
        router.replace('/errors/something-went-wrong');
        return;
      }
    } catch (error: any) {
      logger.error('[Auth]: OAuth login failed', error);

      loginFailCount.current += 1;
      logger.warn('[Auth]: Login fail count:', loginFailCount.current);
    }
  };

  const checkPermissions = async (): Promise<void> => {
    const systemInfoResult = await Promise.resolve({ type: 'auth/getSystemInfo/rejected', error: 'nope' });
    if (systemInfoResult.type === 'auth/getSystemInfo/rejected') {
      logger.error('[Auth]: Failed to get system info:', systemInfoResult.error);
      router.replace('/errors/something-went-wrong');
      return;
    }
  };

  useEffect(() => {
    if (!pathname.startsWith('/errors/') && !pathname.startsWith('/auth/')) {
      checkPermissions().catch(() => {
      });
    }
  }, []);

  useEffect(() => {
    if (!hasTriedOAuth.current && config.featureFlags.bypassBrowser.enabled) {
      hasTriedOAuth.current = true;
      handleOAuthLogin().catch((error) => {
        logger.error('[Auth]: OAuth login failed on navigation', error);
      });
    }
  }, [pathname]);

  return <>{children}</>;
}
