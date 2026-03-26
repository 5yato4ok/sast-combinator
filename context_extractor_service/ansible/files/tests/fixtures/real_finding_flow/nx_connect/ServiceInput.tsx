import { moveToNextFocusable } from "../../helpers";

export function ServiceInput(): React.JSX.Element {
    if (!moveToNextFocusable()) {
        handleInputBlur();
    }
    return <div />;
}
