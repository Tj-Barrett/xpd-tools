import { InputCheckBox } from '@/components/themed';
import type { Preset } from '@/api/autonomous/types';
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
    /**
     * Dropdown options by dotted path (e.g. 'xray.objective_function'), for this field and
     * those nested in it; a null option is shown as "(none)".
     */
    choices?: Record<string, (string | null)[]>;
    /**
     * Preset values by dotted path (e.g. 'run.local.simulated'): a dropdown sets the whole
     * field to one, and an object value's settings are shown below it.
     */
    presets?: Record<string, Preset[]>;
    /** The enclosing group is already dimmed, so don't dim again. */
    parentDisabled?: boolean;
    onChange: (path: (string | number)[], value: Json) => void;
};

// Fields kept in the JSON but not shown: n_points must be 1 (one point per plan run).
const HIDDEN = new Set(['run.n_points']);
// Keys hidden in every experiment pump entry: the pump's own stop limit (target_ml,
// switched on by set_target), not something to change on the day.
const HIDDEN_EXPERIMENT_KEYS = new Set(['target_ml', 'set_target']);
const hidden = (path: (string | number)[], key: string) =>
    HIDDEN.has([...path, key].join('.')) ||
    (path[0] === 'experiment' && HIDDEN_EXPERIMENT_KEYS.has(key));

const isObject = (value: Json): value is Record<string, Json> =>
    value !== null && typeof value === 'object' && !Array.isArray(value);

/**
 * The preset `value` belongs to: the null one for null; otherwise the object preset with
 * exactly the value's fields (just picked), else the one whose fields are most filled in
 * (e.g. min_correlation set -> the correlation option).
 */
export function matchPreset(options: Preset[], value: Json): number {
    if (!isObject(value)) return options.findIndex((option) => option.value === null);
    const fields = Object.keys(value).sort().join();
    let best = -1;
    let bestScore = -1;
    options.forEach((option, i) => {
        if (!isObject(option.value)) return;
        const keys = Object.keys(option.value);
        const score =
            keys.sort().join() === fields
                ? Infinity
                : keys.filter((field) => value[field] != null).length;
        if (score > bestScore) [best, bestScore] = [i, score];
    });
    return best;
}

/** Render one config value as an input, recursing into objects and arrays. */
export default function ConfigField({
    name,
    value,
    path,
    disabled,
    depth = 0,
    parentDisabled = false,
    choices,
    presets,
    onChange,
}: ConfigFieldProps) {
    const dim = disabled && !parentDisabled ? 'opacity-50' : '';
    const key = path.join('.');
    const options = presets?.[key];
    if (options) {
        const selected = matchPreset(options, value);
        const { [key]: _, ...nested } = presets!;
        // Under the dropdown: the value's fields, minus empty ones the chosen option
        // doesn't use (e.g. a correlation target hides max_fwhm/min_plqy).
        const used = new Set(Object.keys((options[selected]?.value as object | null) ?? {}));
        const shown =
            isObject(value) &&
            Object.fromEntries(
                Object.entries(value).filter(([field, item]) => item !== null || used.has(field)),
            );
        return (
            <>
                <label className={`${FIELD} ${dim}`}>
                    <span>{name}</span>
                    <select
                        className={INPUT}
                        value={selected}
                        disabled={disabled}
                        onChange={(e) => onChange(path, options[Number(e.target.value)].value)}
                    >
                        {options.map((option, i) => (
                            <option key={option.label} value={i}>
                                {option.label}
                            </option>
                        ))}
                    </select>
                </label>
                {shown && (
                    <ConfigField
                        name={`${name} settings`}
                        value={shown}
                        path={path}
                        disabled={disabled}
                        depth={depth}
                        parentDisabled={parentDisabled}
                        choices={choices}
                        presets={nested}
                        onChange={onChange}
                    />
                )}
            </>
        );
    }
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
    const listed = choices?.[path.join('.')];
    if (listed && (value === null || typeof value === 'string')) {
        // Keep a value that isn't in the list (e.g. an absolute path) selectable.
        const options = listed.includes(value) ? listed : [value, ...listed];
        return (
            <label className={`${FIELD} ${dim}`}>
                <span>{name}</span>
                <select
                    className={INPUT}
                    value={value ?? ''}
                    disabled={disabled}
                    onChange={(e) => onChange(path, e.target.value === '' ? null : e.target.value)}
                >
                    {options.map((option) => (
                        <option key={option ?? ''} value={option ?? ''}>
                            {option ?? '(none)'}
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
    // Objects list their single values first, then their sub-tiles, so the loose fields
    // (e.g. xray's screening, objective_function) sit together. Lists keep their order.
    // Preset dropdowns (run.local.simulated) count as single values whatever they hold,
    // so picking an option doesn't move them.
    const tile = (field: string, item: Json) =>
        isGroup(item) && !presets?.[[...path, field].join('.')];
    const entries = Array.isArray(value)
        ? value.map((item, i) => [String((item as any)?.name ?? i), item] as const)
        : [
              ...Object.entries(value).filter(([field, item]) => !tile(field, item)),
              ...Object.entries(value).filter(([field, item]) => tile(field, item)),
          ];
    return (
        <ConfigGroup name={name} depth={depth} dim={dim !== ''}>
            {entries
                .filter(([key]) => !hidden(path, key))
                .map(([key, item], i) => (
                    <ConfigField
                        key={key + i}
                        name={key}
                        value={item}
                        path={[...path, Array.isArray(value) ? i : key]}
                        disabled={disabled}
                        depth={depth + 1}
                        parentDisabled={disabled}
                        choices={choices}
                        presets={presets}
                        onChange={onChange}
                    />
                ))}
        </ConfigGroup>
    );
}
