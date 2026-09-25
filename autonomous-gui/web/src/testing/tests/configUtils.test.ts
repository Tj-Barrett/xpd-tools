import { describe, expect, it } from 'vitest';
import { parseText, setAt } from '@/utils/configUtils';

describe('setAt', () => {
    it('replaces a nested value without mutating the original', () => {
        const config = { xray: { settings: { exposure: 5 } }, pumps: [{ bounds: [10, 200] }] };
        const next = setAt(config, ['xray', 'settings', 'exposure'], 600) as any;
        expect(next.xray.settings.exposure).toBe(600);
        expect(config.xray.settings.exposure).toBe(5);
        expect(next.pumps).toBe(config.pumps); // untouched branches are shared
    });

    it('indexes into arrays and keeps them arrays', () => {
        const next = setAt(
            { pumps: [{ bounds: [10, 200] }] },
            ['pumps', 0, 'bounds', 1],
            150,
        ) as any;
        expect(next.pumps[0].bounds).toEqual([10, 150]);
        expect(Array.isArray(next.pumps)).toBe(true);
    });

    it('returns the value itself for an empty path', () => {
        expect(setAt({ a: 1 }, [], 7)).toBe(7);
    });
});

describe('parseText', () => {
    it.each([
        ['', null],
        ['   ', null],
        ['0.9', 0.9],
        ['true', true],
        ['[1, 2]', [1, 2]],
        ['{"a": 1}', { a: 1 }],
        ['null', null],
        ['xpd', 'xpd'],
    ])('parses %j as %j', (text, expected) => {
        expect(parseText(text)).toEqual(expected);
    });
});
