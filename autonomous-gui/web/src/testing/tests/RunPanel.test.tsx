import { fireEvent, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import RunPanel from '@/features/RunPanel';
import { makeState, makeTrials } from '@/stories/mocks';
import { apiCalls, renderWithServer } from '../renderWithServer';

const button = (name: string) => screen.getByRole('button', { name });

describe('RunPanel', () => {
    afterEach(() => vi.restoreAllMocks());

    it('shows the status, mode, and progress', async () => {
        renderWithServer(<RunPanel />, {
            state: makeState({
                status: 'running',
                editable: ['success_criteria'],
                trials: makeTrials(12),
            }),
        });
        expect(await screen.findByText('running')).toBeInTheDocument();
        expect(screen.getByText('Queue Server')).toBeInTheDocument();
        expect(screen.getByText(/12 trials · 40 iterations/)).toBeInTheDocument();
    });

    it.each([
        ['loaded', { Build: true, Run: false, Stop: false, Clear: false }],
        ['built', { Build: true, Run: true, Stop: false, Clear: true }],
        ['running', { Build: false, Run: false, Stop: true, Clear: false }],
        ['stopping', { Build: false, Run: false, Stop: false, Clear: false }],
        ['stopped', { Build: true, Run: true, Stop: false, Clear: true }],
    ] as const)('enables the right buttons when %s', async (status, enabled) => {
        renderWithServer(<RunPanel />, { state: makeState({ status }) });
        await screen.findByText(status);
        for (const [name, isEnabled] of Object.entries(enabled)) {
            expect(button(name), name)[isEnabled ? 'toBeEnabled' : 'toBeDisabled']();
        }
    });

    it('explains why Clear is disabled', async () => {
        renderWithServer(<RunPanel />, { state: makeState({ status: 'running' }) });
        expect(
            await screen.findByText('Stop the campaign and let it end to enable Clear'),
        ).toBeInTheDocument();
    });

    it('Build posts to the server and shows the new status', async () => {
        const { fetch } = renderWithServer(<RunPanel />, { state: makeState() });
        fireEvent.click(await screen.findByRole('button', { name: 'Build' }));
        expect(await screen.findByText('built')).toBeInTheDocument();
        expect(apiCalls(fetch)).toContainEqual(['POST', '/api/build']);
    });

    it('Clear asks first and does nothing if cancelled', async () => {
        const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
        const { fetch } = renderWithServer(<RunPanel />, {
            state: makeState({ status: 'stopped' }),
        });
        fireEvent.click(await screen.findByRole('button', { name: 'Clear' }));
        expect(confirm).toHaveBeenCalled();
        expect(apiCalls(fetch)).not.toContainEqual(['POST', '/api/clear']);
    });

    it('Clear, once confirmed, clears and says so', async () => {
        vi.spyOn(window, 'confirm').mockReturnValue(true);
        renderWithServer(<RunPanel />, {
            state: makeState({ status: 'stopped', trials: makeTrials(3) }),
        });
        fireEvent.click(await screen.findByRole('button', { name: 'Clear' }));
        expect(
            await screen.findByText(/Cleared: the built agent and its trials were dropped/),
        ).toBeInTheDocument();
    });

    it('shows the last campaign error', async () => {
        renderWithServer(<RunPanel />, {
            state: makeState({ status: 'failed', error: 'ConnectionError(boom)' }),
        });
        expect(await screen.findByText('Last error: ConnectionError(boom)')).toBeInTheDocument();
    });

    it('says when server.py is unreachable', async () => {
        renderWithServer(<RunPanel />, { state: makeState(), offline: true });
        await waitFor(() => expect(screen.getByText(/Can't reach server.py/)).toBeInTheDocument());
    });

    it('shows the historical file and splits historical from new trials', async () => {
        renderWithServer(<RunPanel />, {
            state: makeState({
                status: 'running',
                trials: makeTrials(20),
                historical: { path: '/beamline/configs/agent_halide_data.csv', count: 12 },
            }),
        });
        expect(await screen.findByText('agent_halide_data.csv')).toBeInTheDocument();
        expect(screen.getByText(/12 trials ingested/)).toBeInTheDocument();
        expect(screen.getByText(/12 historical \+ 8 new trials/)).toBeInTheDocument();
    });

    it('says when there is no historical data', async () => {
        renderWithServer(<RunPanel />, { state: makeState() });
        const row = (await screen.findByText('Historical')).nextElementSibling!;
        expect(row).toHaveTextContent('none');
    });
});
