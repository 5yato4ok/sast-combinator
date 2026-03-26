export default function RootLayoutClient({ children }: { children: ReactNode }) {
	const [isMenuCollapsed, setIsMenuCollapsed] = useState<boolean>(false);
	return children;
}
