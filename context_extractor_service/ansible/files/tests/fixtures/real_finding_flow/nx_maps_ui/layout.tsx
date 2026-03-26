'use client';

import React from 'react';
import { config } from '@/config';
import { AuthGuard } from '@/components/auth/auth-guard';

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        {React.createElement('meta', {
          name: 'version',
          value: config.version
        })}
      </head>
      <body>
        <AuthGuard>
          {children}
        </AuthGuard>
      </body>
    </html>
  );
}
