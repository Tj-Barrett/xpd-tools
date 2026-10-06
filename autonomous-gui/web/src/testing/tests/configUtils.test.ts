import { describe, expect, it } from 'vitest';
import { inapplicableFields, parseText, setAt } from '@/utils/configUtils';

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

describe('inapplicableFields', () => {
    const phase = { name: 'A', target_fraction: null, fraction_tolerance: 0.05 };
    const xray = { cnn_dataset_path: null, cnn_weights_path: null, fraction_mode: false };

    it('hides cnn settings and targets for a non-cnn objective', () => {
        const hide = inapplicableFields({
            xray: { ...xray, objective_function: 'pearson', phases: [phase] },
        });
        expect([...hide].sort()).toEqual([
            'xray.cnn_dataset_path',
            'xray.cnn_weights_path',
            'xray.fraction_mode',
            'xray.phases.0.fraction_tolerance',
            'xray.phases.0.target_fraction',
        ]);
    });

    it('shows targets in fraction_mode', () => {
        const config = {
            xray: { ...xray, objective_function: 'cnn', fraction_mode: true, phases: [phase] },
        };
        expect(inapplicableFields(config).size).toBe(0);
    });

    it('keeps a leftover value visible so it can be cleared', () => {
        const hide = inapplicableFields({
            xray: {
                ...xray,
                objective_function: 'cnn',
                phases: [{ ...phase, target_fraction: 0.5 }],
            },
        });
        expect([...hide]).toEqual(['xray.phases.0.fraction_tolerance']);
    });
});
