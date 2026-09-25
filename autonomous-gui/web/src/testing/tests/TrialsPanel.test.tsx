import { screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import TrialsPanel from '@/features/TrialsPanel';
import { makeState, makeTrials } from '@/stories/mocks';
import { renderWithServer } from '../renderWithServer';

describe('TrialsPanel', () => {
    it('says when there are no trials', async () => {
        renderWithServer(<TrialsPanel />, { state: makeState() });
        expect(await screen.findByText('No trials yet.')).toBeInTheDocument();
    });

    it('lists trials newest first with rounded numbers', async () => {
        const trials = makeTrials(40);
        renderWithServer(<TrialsPanel />, { state: makeState({ status: 'finished', trials }) });
        expect(await screen.findByText('Trials (40)')).toBeInTheDocument();
        const rows = within(screen.getByRole('table')).getAllByRole('row');
        expect(rows).toHaveLength(41); // header + 40
        const cells = within(rows[1]).getAllByRole('cell');
        expect(cells[0]).toHaveTextContent('39');
        // corr_CsPbBr3, shown to 4 significant figures
        expect(cells[4]).toHaveTextContent(String(Number(trials[39].corr_CsPbBr3.toPrecision(4))));
    });

    it('draws the divider above the newest historical row', async () => {
        renderWithServer(<TrialsPanel />, {
            state: makeState({
                status: 'running',
                trials: makeTrials(20),
                historical: { path: '/beamline/configs/agent_halide_data.csv', count: 12 },
            }),
        });
        const rows = within(await screen.findByRole('table')).getAllByRole('row');
        const marked = rows.filter((row) => row.className.includes('border-dashed'));
        expect(marked).toHaveLength(1);
        expect(within(marked[0]).getAllByRole('cell')[0]).toHaveTextContent('11');
    });
});
