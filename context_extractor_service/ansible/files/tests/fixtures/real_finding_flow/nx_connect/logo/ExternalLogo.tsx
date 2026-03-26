type LogoProps = {
	configData: ConfigInterface | null;
}

const Logo = ({ configData }: LogoProps) => {
	const { theme, systemTheme } = useTheme();
	return configData || theme || systemTheme;
};

export default Logo;
