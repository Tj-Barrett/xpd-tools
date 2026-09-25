import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import LoadConfig from '@/components/LoadConfig';
import { makeState } from '@/stories/mocks';
import { renderWithServer } from '../renderWithServer';

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
});
