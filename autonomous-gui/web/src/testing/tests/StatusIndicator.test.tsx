import { screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import StatusIndicator from '@/components/StatusIndicator';
import { makeState } from '@/stories/mocks';
import { renderWithServer } from '../renderWithServer';

describe('StatusIndicator', () => {
    afterEach(() => vi.restoreAllMocks());

    it.each([
        ['empty', 'Waiting'],
        ['built', 'Waiting'],
        ['finished', 'Waiting'],
        ['stopped', 'Waiting'],
        ['running', 'Running'],
        ['stopping', 'Running'],
        ['failed', 'Failed'],
    ] as const)('shows %s as %s', async (status, label) => {
        renderWithServer(<StatusIndicator />, { state: makeState({ status }) });
        expect(await screen.findByText(label)).toHaveAttribute('role', 'status');
    });

    it('blinks only when failed', async () => {
        renderWithServer(<StatusIndicator />, { state: makeState({ status: 'failed' }) });
        expect(await screen.findByText('Failed')).toHaveClass('animate-pulse');
    });

    it('shows Failed when the server is unreachable', async () => {
        renderWithServer(<StatusIndicator />, { state: makeState(), offline: true });
        expect(await screen.findByText('Failed')).toHaveAttribute(
            'title',
            expect.stringMatching(/Can't reach server.py/),
        );
    });
});
