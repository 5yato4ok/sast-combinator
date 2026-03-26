import './styles.scss';

export default function Logo() {
		const { theme, systemTheme } = useTheme();
		const configData = useConfig();
		const currentTheme = getTheme(theme, systemTheme);
		const logoPath = currentTheme === 'dark' ? configData.LOGO_DARK : configData.LOGO_LIGHT;
		console.log('logoPath', logoPath);
		return logoPath ? `${window.location.origin}/${logoPath}` : '';
}
