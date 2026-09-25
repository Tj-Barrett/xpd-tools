import type { ReactElement } from 'react';
import { render } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router';
import { vi } from 'vitest';
import { mockFetch, type MockServer } from '@/stories/mocks';

/**
 * Render `ui` against the same fake server.py the stories use.
 *
 * Args:
 *   - ui: The component to render.
 *   - server: The fake server's state, configs, or offline flag.
 *
 * Returns:
 *   - The render result plus `fetch`, a spy recording every /api call.
 */
export function renderWithServer(ui: ReactElement, server?: MockServer) {
    const fetch = vi.fn(mockFetch(server));
    window.fetch = fetch;
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const result = render(
        <MemoryRouter>
            <QueryClientProvider client={client}>{ui}</QueryClientProvider>
        </MemoryRouter>,
    );
    return { ...result, fetch };
}

/** The [method, path] of every /api call the spy saw, e.g. ['POST', '/api/build']. */
export function apiCalls(fetch: ReturnType<typeof vi.fn>) {
    return fetch.mock.calls.map(([url, init]) => [
        (init as RequestInit | undefined)?.method ?? 'GET',
        String(url),
    ]);
}
