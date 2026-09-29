import { fireEvent, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import LoadConfig from '@/components/LoadConfig';
import ConfigPanel from '@/features/ConfigPanel';
import { makeState } from '@/stories/mocks';
import { apiCalls, renderWithServer } from '../renderWithServer';

describe('LoadConfig', () => {
    it('disables Load until a config is chosen', async () => {
        renderWithServer(<LoadConfig />, { state: makeState(), configs: ['a.json', 'b.json'] });
        expect(await screen.findByText('Choose a config…')).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'Load' })).toBeDisabled();
    });

    it('says when the config directory has no JSON files', async () => {
        renderWithServer(<LoadConfig />, { state: makeState(), configs: [] });
        expect(await screen.findByText('No .json files found')).toBeInTheDocument();
    });

    it('blocks loading while a campaign runs', async () => {
        renderWithServer(<LoadConfig />, { state: makeState({ status: 'running' }) });
        expect(
            await screen.findByText('Stop the campaign to load another config.'),
        ).toBeInTheDocument();
    });

    it('asks before dropping unapplied Config edits', async () => {
        const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
        const { fetch } = renderWithServer(
            <>
                <ConfigPanel />
                <LoadConfig />
            </>,
            { state: makeState(), configs: ['a.json', 'b.json'] },
        );
        const iterations = (await screen.findByText('iterations'))
            .closest('label')!
            .querySelector('input')!;
        fireEvent.change(iterations, { target: { value: '12' } });
        fireEvent.click(screen.getByText('Choose a config…'));
        fireEvent.click(await screen.findByText('b.json'));
        fireEvent.click(screen.getByRole('button', { name: 'Load' }));
        expect(confirm).toHaveBeenCalledWith(
            'Loading drops your unapplied Config changes. Continue?',
        );
        expect(apiCalls(fetch)).not.toContainEqual(['POST', '/api/load']); // declined
        confirm.mockRestore();
    });

    it('holds Load while the server builds', async () => {
        renderWithServer(<LoadConfig />, { state: makeState({ building: true }) });
        expect(
            await screen.findByText('Building the agent: Load is available once it finishes.'),
        ).toBeInTheDocument();
    });
});
