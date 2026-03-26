export const moveToNextFocusableByElementId = (elementId: string | undefined, changeFocusDelay: number = 100) => {
    if (elementId) {
        setTimeout(() => {
            const nextFocusable = document.getElementById(elementId);
            if (nextFocusable) {
                nextFocusable.focus();
            }
        }, changeFocusDelay);
    }
};

export const findDemoService = (services: CpServicesOwned[]) => {
    return services.find((s) => {
        return s.subType === 'demo' && s.type === 'local_recording';
    });
};
