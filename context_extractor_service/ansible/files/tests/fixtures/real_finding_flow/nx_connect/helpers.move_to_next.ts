import { focusElement } from "./focus";

export const findNextFocusable = () => document.querySelector('[tabindex]');

export const moveToNextFocusable = () => {
    const nextFocusable = findNextFocusable();
    if (nextFocusable) {
        focusElement(nextFocusable);
        return true;
    }

    return false;
};
