export const authenticateTwoFactorFactory =
    (
        cloudApi: NxCloudApiService,
        accountService: NxAccountService,
        handleWindowRef: (opened: Window) => void = () => {},
    ) =>
    async () => {
        const accessToken = await lastValueFrom(cloudApi.getAccessToken());
        const oauthUrl = getOauthUrl({
            state: 'system2faAuth',
            email: accountService.account.email,
            accessToken,
        });
        const opened = window.open(oauthUrl, '_blank')!;
        handleWindowRef(opened);
        let authenticated = false;
        await new Promise<void>(resolve => {
            const checkingIfOpen = timer(2_500, 1000).subscribe(() => {
                if (opened.closed) {
                    resolve();
                    checkingIfOpen.unsubscribe();
                }
            });

            window.addEventListener('message', (event: MessageEvent<'authenticated'>) => {
                if (event.data === 'authenticated') {
                    authenticated = true;
                    opened.close();
                    defer(() => cloudApi.getAllAccountInfo(true))
                        .pipe(
                            map(({ account2faEnabled }) => {
                                if (!account2faEnabled) {
                                    throw new Error('Waiting for cache to update');
                                }
                            }),
                            retry({
                                delay: 500,
                                count: 10,
                            }),
                            delay(500),
                            catchError(() => Promise.resolve()),
                        )
                        .subscribe(() => {
                            reloadWindowsChannel.reloadAllWindows(true, 'sessionVerified');
                        });
                }
            });
        });
        return authenticated;
    };
