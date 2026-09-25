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
