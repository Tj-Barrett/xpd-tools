import { InputCheckBox } from '@/components/themed';
import { Json } from '@/types/json';
import { parseText } from '@/utils/configUtils';

const FIELD = 'grid grid-cols-[14rem_1fr] items-center gap-3';
const INPUT =
    'max-w-sm rounded border border-line bg-surface px-1.5 py-0.5 disabled:cursor-not-allowed disabled:bg-surface-disabled';

// Tile shade per nesting depth (colors.ts `nest`); full names so Tailwind finds them.
const NEST_BG = ['bg-nest-1', 'bg-nest-2', 'bg-nest-3'];

/** Whether a value is shown as a collapsible tile (objects and lists of objects). */
export function isGroup(value: Json): boolean {
    if (value === null || typeof value !== 'object') return false;
    return !Array.isArray(value) || value.some((item) => typeof item === 'object' && item !== null);
}

/** A collapsible tile, shaded by how deeply it is nested. */
export function ConfigGroup({
    name,
    depth,
    dim,
    children,
}: {
    name: string;
    depth: number;
    dim: boolean;
    children: React.ReactNode;
}) {
    return (
        // <details> collapses natively; open by default, and the browser keeps each
        // group's open/closed state across the 2 s polls.
        <details
            className={`rounded-md border border-line px-3 py-1.5 ${NEST_BG[depth % NEST_BG.length]} ${dim ? 'opacity-50' : ''}`}
            open
        >
            <summary className="cursor-pointer font-semibold">{name}</summary>
            <div className="flex flex-col gap-1.5 pb-1 pt-1.5">{children}</div>
        </details>
    );
}

export type ConfigFieldProps = {
    name: string;
    value: Json;
    path: (string | number)[];
    disabled: boolean;
    /** Nesting depth: 0 for a top-level tile, +1 for each tile it sits in. */
    depth?: number;
    /** Offer these values in a dropdown instead of a text box (plus "(none)" for null). */
    choices?: string[];
    /** The enclosing group is already dimmed, so don't dim again. */
    parentDisabled?: boolean;
    onChange: (path: (string | number)[], value: Json) => void;
};

/** Render one config value as an input, recursing into objects and arrays. */
export default function ConfigField({
    name,
    value,
    path,
    disabled,
    depth = 0,
    parentDisabled = false,
    choices,
    onChange,
}: ConfigFieldProps) {
    const dim = disabled && !parentDisabled ? 'opacity-50' : '';
    if (typeof value === 'boolean') {
        return (
            <div className={`${FIELD} ${dim}`}>
                <InputCheckBox
                    label={name}
                    isChecked={value}
                    cb={(checked) => !disabled && onChange(path, checked)}
                />
            </div>
        );
    }
    if (typeof value === 'number') {
        return (
            <label className={`${FIELD} ${dim}`}>
                <span>{name}</span>
                <input
                    type="number"
                    className={INPUT}
                    value={value}
                    disabled={disabled}
                    onChange={(e) =>
                        onChange(path, e.target.value === '' ? null : Number(e.target.value))
                    }
                />
            </label>
        );
    }
    if (choices && (value === null || typeof value === 'string')) {
        // Keep a value that isn't in the list (e.g. an absolute path) selectable.
        const options = value === null || choices.includes(value) ? choices : [value, ...choices];
        return (
            <label className={`${FIELD} ${dim}`}>
                <span>{name}</span>
                <select
                    className={INPUT}
                    value={value ?? ''}
                    disabled={disabled}
                    onChange={(e) => onChange(path, e.target.value === '' ? null : e.target.value)}
                >
                    <option value="">(none)</option>
                    {options.map((option) => (
                        <option key={option} value={option}>
                            {option}
                        </option>
                    ))}
                </select>
            </label>
        );
    }
    if (value === null || typeof value === 'string') {
        return (
            <label className={`${FIELD} ${dim}`}>
                <span>{name}</span>
                <input
                    type="text"
                    className={INPUT}
                    value={value ?? ''}
                    placeholder="null"
                    disabled={disabled}
                    onChange={(e) =>
                        onChange(
                            path,
                            typeof value === 'string' ? e.target.value : parseText(e.target.value),
                        )
                    }
                />
            </label>
        );
    }
    if (Array.isArray(value) && value.every((item) => typeof item !== 'object' || item === null)) {
        // Short scalar lists such as bounds or ranges: one input per item.
        return (
            <label className={`${FIELD} ${dim}`}>
                <span>{name}</span>
                <span className="flex gap-2">
                    {value.map((item, i) => (
                        <input
                            key={i}
                            className={`${INPUT} w-28`}
                            type={typeof item === 'number' ? 'number' : 'text'}
                            value={(item as string | number | null) ?? ''}
                            disabled={disabled}
                            onChange={(e) =>
                                onChange(
                                    [...path, i],
                                    typeof item === 'number'
                                        ? Number(e.target.value)
                                        : e.target.value,
                                )
                            }
                        />
                    ))}
                </span>
            </label>
        );
    }
    const entries = Array.isArray(value)
        ? value.map((item, i) => [String((item as any)?.name ?? i), item] as const)
        : Object.entries(value);
    return (
        <ConfigGroup name={name} depth={depth} dim={dim !== ''}>
            {entries.map(([key, item], i) => (
                <ConfigField
                    key={key + i}
                    name={key}
                    value={item}
                    path={[...path, Array.isArray(value) ? i : key]}
                    disabled={disabled}
                    depth={depth + 1}
                    parentDisabled={disabled}
                    onChange={onChange}
                />
            ))}
        </ConfigGroup>
    );
}
