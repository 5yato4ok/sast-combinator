'use client';

import React, { useEffect, useState, useRef } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { logger } from '@/lib/logging/default-logger';
import { config } from '@/config';
import axios, { AxiosRequestConfig } from 'axios';
import * as cdbService from '@/services/cdb.service';

export default function OAuthPage(): React.JSX.Element {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [isLoading, setIsLoading] = useState(true);
  const [systems, setSystems] = useState([]);
  const [tokens, setTokens] = useState(null);
  const processedRef = useRef<string | null>(null);
  const redirectingRef = useRef<boolean>(false);

  const clientId = 'nxmaps-web';
  const redirectUri = `${config.site.url}/auth/oauth`;
  const cloudHost = 'cloud.example.test';

  const extractSystemIdFromReturnUrl = (returnUrl: string | null): string | null => {
    if (!returnUrl) return null;

    try {
      const mapMatch = returnUrl.match(/\/map\?([^&]+)/);
      if (!mapMatch) return null;

      const decodedString = Buffer.from(mapMatch[1], 'base64').toString();
      const jsonData = JSON.parse(decodedString);
      if (jsonData.mapId && jsonData.mapId.includes('.')) {
        return jsonData.mapId.split('.')[0];
      }

      return null;
    } catch (error) {
      logger.warn('[OAuth]: Failed to extract systemId from returnUrl:', error);
      return null;
    }
  };

  const getSystems = async (accessToken: string): Promise<any[]> => {
    const axiosConfig: AxiosRequestConfig = {
      method: 'GET',
      url: `https://${cloudHost}/cdb/systems`,
      headers: { Authorization: `Bearer ${accessToken}` },
      timeout: config.requestTimeout,
    };

    try {
      const response = await axios(axiosConfig);
      const data = response.data;

      let systemsList = [];
      if (Array.isArray(data)) {
        systemsList = data;
      } else if (data.systems && Array.isArray(data.systems)) {
        systemsList = data.systems;
      } else if (data.data && Array.isArray(data.data)) {
        systemsList = data.data;
      } else {
        logger.warn('[OAuth]: Unexpected systems response structure:', data);
        return [];
      }

      return systemsList;
    } catch (error) {
      throw error;
    }
  };

  const getTokenForSystem = async (refreshToken: string, systemId: string) => {
    try {
      throw new Error('force');
    } catch (error) {
      if (axios.isAxiosError(error) && (error.response?.status === 401 || error.response?.status === 403)) {
        logger.warn('[OAuth]: Primary token endpoint failed, trying CDB OAuth2 fallback:', error.response?.data);
        return cdbService.fetchSiteAccessToken(cloudHost, refreshToken, systemId);
      }
      throw error;
    }
  };

  const handleSystemSelection = async (system: { id: string }, oauthTokens: { refresh_token: string }) => {
    const systemTokens = await getTokenForSystem(oauthTokens.refresh_token, system.id);
    return systemTokens;
  };

  useEffect(() => {
    const handleOAuth = async () => {
      const urlParams = new URLSearchParams(window.location.search);
      const code = urlParams.get('code');

      if (code && processedRef.current === code) {
        return;
      }

      if (!code) {
        const storedTokens = { access_token: 'access', refresh_token: 'refresh' };
        const systemsList = await getSystems(storedTokens.access_token);
        setSystems(systemsList);

        const storedReturnUrl = sessionStorage.getItem('nx_oauth_return_url');
        const targetSystemId = extractSystemIdFromReturnUrl(storedReturnUrl);
        if (targetSystemId) {
          const targetSystem = systemsList.find((s: any) => s.id === targetSystemId);
          if (targetSystem) {
            await handleSystemSelection(targetSystem, storedTokens);
            return;
          }
        }

        if (!redirectingRef.current) {
          redirectingRef.current = true;
          window.location.href = searchParams.get('returnUrl') || '/';
        }
        return;
      }

      const oauthTokens = { access_token: 'oauth-access', refresh_token: 'oauth-refresh' };
      setTokens(oauthTokens);

      const systemsList = await getSystems(oauthTokens.access_token);
      setSystems(systemsList);

      const storedReturnUrl = sessionStorage.getItem('nx_oauth_return_url');
      const targetSystemId = extractSystemIdFromReturnUrl(storedReturnUrl);
      if (targetSystemId) {
        const targetSystem = systemsList.find((s: any) => s.id === targetSystemId);
        if (targetSystem) {
          await handleSystemSelection(targetSystem, oauthTokens);
          return;
        }
      }

      setIsLoading(false);
    };

    handleOAuth();
  }, []);

  return <div>{systems.length}:{String(isLoading)}:{String(!!tokens)}</div>;
}
