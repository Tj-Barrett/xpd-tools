import { Json } from '@/types/json';

/** Return a copy of `root` with the value at `path` replaced. */
export function setAt(root: Json, path: (string | number)[], value: Json): Json {
    if (path.length === 0) return value;
    const [head, ...rest] = path;
    const copy: any = Array.isArray(root) ? [...root] : { ...(root as object) };
    copy[head] = setAt(copy[head], rest, value);
    return copy;
}

/** Parse a text box: empty is null, JSON if it parses, otherwise the raw string. */
export function parseText(text: string): Json {
    if (text.trim() === '') return null;
    try {
        return JSON.parse(text);
    } catch {
        return text;
    }
}

/**
 * Dotted paths of fields that don't apply to `config`, to hide on the Config page: cnn's
 * settings unless objective_function is 'cnn', a phase's target unless fraction_mode is on.
 * A field still holding a value stays shown, so a leftover that Apply rejects can be cleared.
 */
export function inapplicableFields(config: Record<string, Json>): Set<string> {
    const xray = (config.xray ?? {}) as Record<string, Json>;
    const hide = new Set<string>();
    const unless = (applies: boolean, path: string, value: Json | undefined) => {
        if (!applies && (value == null || value === false)) hide.add(path);
    };
    for (const key of ['cnn_dataset_path', 'cnn_weights_path', 'fraction_mode'])
        unless(xray.objective_function === 'cnn', `xray.${key}`, xray[key]);
    ((xray.phases ?? []) as Record<string, Json>[]).forEach((phase, i) => {
        unless(
            xray.fraction_mode === true,
            `xray.phases.${i}.target_fraction`,
            phase.target_fraction,
        );
        // A tolerance alone does nothing, so it hides whatever its value.
        unless(xray.fraction_mode === true, `xray.phases.${i}.fraction_tolerance`, null);
    });
    return hide;
}
