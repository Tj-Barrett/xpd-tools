import type { Action, AppState } from '@/api/autonomous/types';
import { mockConfig } from './mockConfig';

/** What the fake server.py answers with in a story. */
export type MockServer = {
    state: AppState;
    configs?: string[];
    /** Historical-data CSVs offered for agent_data_path. */
    csvs?: string[];
    /** Every /api call fails as if server.py weren't running. */
    offline?: boolean;
};

const CONFIG_PATH = '/beamline/configs/autonomous_build_config.json';

/** A plausible AppState; override any field. */
export function makeState(overrides: Partial<AppState> = {}): AppState {
    return {
        status: 'loaded',
        error: null,
        mode: 'queue_server',
        config_dir: '/beamline/configs',
        config_path: CONFIG_PATH,
        config: mockConfig,
        editable: 'all',
        trials: [],
        trials_path: null,
        historical: { path: null, count: null },
        ...overrides,
    };
}

/** Deterministic pseudo-random numbers so stories look the same every time. */
function seeded(seed: number) {
    return () => {
        seed = (seed * 16807) % 2147483647;
        return seed / 2147483647;
    };
}

/** `n` Ax-summarize-shaped trials for the mock config's phases and pumps. */
export function makeTrials(n: number, { lastFailed = false } = {}): Record<string, any>[] {
    const random = seeded(7);
    return Array.from({ length: n }, (_, i) => {
        const progress = i / Math.max(n - 1, 1);
        return {
            trial_index: i,
            arm_name: `${i}_0`,
            trial_status: lastFailed && i === n - 1 ? 'FAILED' : 'COMPLETED',
            generation_node: i === 0 ? 'CenterOfSearchSpace' : i < 6 ? 'Sobol' : 'MBM',
            corr_CsPbBr3: lastFailed && i === n - 1 ? null : 0.4 + 0.5 * progress + 0.1 * random(),
            corr_CsBr: 0.6 - 0.4 * progress + 0.1 * random(),
            corr_Cs4PbBr6: 0.3 + 0.2 * random(),
            infusion_rate_CsPb: 10 + 190 * random(),
            infusion_rate_Br: 5 + 195 * random(),
            infusion_rate_I2: 200 * random(),
        };
    });
}

// What each action leaves the status as, so buttons behave plausibly in a story.
const NEXT_STATUS: Record<Exclude<Action, 'config'>, AppState['status']> = {
    build: 'built',
    run: 'running',
    stop: 'stopped',
    clear: 'loaded',
    load: 'loaded',
};

/**
 * A `fetch` replacement serving /api/* from `server`; POSTs update its state.
 *
 * Args:
 *   - server: The story's fake server; undefined means an empty one.
 *
 * Returns:
 *   - typeof fetch - Use as window.fetch.
 */
export function mockFetch(
    server: MockServer = { state: makeState({ status: 'empty', config: null }) },
) {
    let state = server.state;
    const json = (body: unknown, status = 200) =>
        new Response(JSON.stringify(body), {
            status,
            headers: { 'Content-Type': 'application/json' },
        });

    return async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
        const url = String(input);
        if (!url.startsWith('/api')) return new Response('not mocked', { status: 404 });
        if (server.offline) throw new TypeError('Failed to fetch');
        const path = url.slice('/api/'.length);
        const method = init?.method ?? 'GET';
        console.info('[mock server.py]', method, url, init?.body ?? '');

        if (path === 'state') return json(state);
        if (path === 'configs') return json(server.configs ?? ['autonomous_build_config.json']);
        if (path === 'csvs')
            return json(
                server.csvs ?? ['agent_halide_data.csv', 'agent_halide_data_uvvis_only.csv'],
            );
        if (path === 'config') {
            state = { ...state, config: JSON.parse(String(init?.body)), config_path: CONFIG_PATH };
            return json(state);
        }
        const next = NEXT_STATUS[path as keyof typeof NEXT_STATUS];
        if (!next) return json({ detail: `Not Found: ${url}` }, 404);
        state = {
            ...state,
            status: next,
            editable: next === 'running' ? ['success_criteria'] : 'all',
            trials: next === 'loaded' ? [] : state.trials,
        };
        return json(state);
    };
}
