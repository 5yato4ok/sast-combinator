import React from 'react';

export function CompanyAndContactInfo() {
	const resizeWindow = () => {
		document.querySelectorAll('.ellipsify').forEach((elem: Element) => {
			if (elem && elem.textContent && (elem as HTMLElement).offsetWidth < elem.scrollWidth) {
				elem.setAttribute('title', elem.textContent);
			}
		});
	};

	useEffect(() => {
		resizeWindow();
	}, []);
}
