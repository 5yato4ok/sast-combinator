import InfoIcon from '@/icons/info.svg';

export default function Alert({ type, ...props }: Alert) {
	return (
		<div className={classnames(styles.alert, styles[type])} {...props}>
			{type === 'info' && (
				<div className={styles.icon}>
					<InfoIcon width={40} height={40} />
				</div>
			)}
			<div className={styles.contentWrapper}>{props.children}</div>
		</div>
	);
}
