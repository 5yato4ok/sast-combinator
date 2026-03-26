import Logo from '@/app/(external)/components/Logo/Logo';

export default function RootLayoutClient({ children }: { children: ReactNode }) {
	const configData = await fetchConfig();

	const loadConfig = async () => {
		const domain = window.location.hostname;
		const trackingID = domain.includes('connect.nxgo.io') ? 'G-ZFX72ZBEEX' : configData?.GOOGLE_ANALYTICS_ID;
		gtagInitialize(trackingID);
	};
	clearConfigCache();
	loadConfig();
	return children || <Logo />;
}
