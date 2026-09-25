// finch components recoloured from src/theme/colors.ts; import these instead of finch's.
// Props are finch's own. Where finch has no prop for a part, a descendant class
// (e.g. `[&_h3]:…`, "any h3 inside") reaches it; those out-rank finch's own classes.
import type { ComponentProps } from 'react';
import {
    Button as FinchButton,
    InputCheckBox as FinchInputCheckBox,
    Paper as FinchPaper,
    SelectDropdown as FinchSelectDropdown,
} from '@blueskyproject/finch';
import type { ButtonProps, PaperProps } from '@blueskyproject/finch';

// Full class names (not built from pieces) so Tailwind finds them when scanning.
const PRIMARY = 'bg-primary hover:bg-primary-hover text-primary-text';
const SECONDARY =
    'bg-secondary hover:bg-secondary-hover text-secondary-text border-secondary-border';

/** finch Button; `className` still wins, e.g. the Stop button's `bg-stop`. */
export function Button({ isSecondary, className = '', ...props }: ButtonProps) {
    return (
        <FinchButton
            isSecondary={isSecondary}
            className={`${isSecondary ? SECONDARY : PRIMARY} ${className}`}
            {...props}
        />
    );
}

/** finch Paper (card), including its title. */
export function Paper({ className = '', ...props }: PaperProps) {
    return (
        <FinchPaper
            className={`bg-card text-card-text [&_h3]:text-card-title ${className}`}
            {...props}
        />
    );
}

/** finch SelectDropdown: the closed box and the open list of options. */
export function SelectDropdown({
    triggerClassName = '',
    contentClassName = '',
    ...props
}: ComponentProps<typeof FinchSelectDropdown>) {
    return (
        <FinchSelectDropdown
            triggerClassName={`text-select ${triggerClassName}`}
            contentClassName={`bg-select-menu [&_[role=option]]:text-select-option ${contentClassName}`}
            {...props}
        />
    );
}

const CHECKBOX =
    '[&_input]:border-checkbox [&_input]:bg-checkbox-box [&_input:checked]:bg-checkbox-box [&_svg]:text-checkbox';
const CHECKBOX_LABEL_ON = '[&_label]:text-checkbox-label [&_label:hover]:text-checkbox-label-hover';
const CHECKBOX_LABEL_OFF =
    '[&_label]:text-checkbox-label-off [&_label:hover]:text-checkbox-label-off-hover';

/** finch InputCheckBox: box, tick, and a label coloured by whether it's ticked. */
export function InputCheckBox({
    className = '',
    isChecked,
    ...props
}: ComponentProps<typeof FinchInputCheckBox>) {
    const label = isChecked ? CHECKBOX_LABEL_ON : CHECKBOX_LABEL_OFF;
    return (
        <FinchInputCheckBox
            isChecked={isChecked}
            className={`${CHECKBOX} ${label} ${className}`}
            {...props}
        />
    );
}
