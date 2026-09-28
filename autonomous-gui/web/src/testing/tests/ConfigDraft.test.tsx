import { useState } from 'react';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import ConfigPanel from '@/features/ConfigPanel';
import RunPanel from '@/features/RunPanel';
import { makeState } from '@/stories/mocks';
import { renderWithServer } from '../renderWithServer';

/** Two "pages" swapped like the app's routes: the hidden one is unmounted. */
function Pages() {
    const [page, setPage] = useState<'config' | 'run'>('config');
    return (
        <>
            <button onClick={() => setPage(page === 'config' ? 'run' : 'config')}>switch</button>
            {page === 'config' ? <ConfigPanel /> : <RunPanel />}
        </>
    );
}

const iterationsInput = async () =>
    (await screen.findByText('iterations')).closest('label')!.querySelector('input')!;

describe('Config draft across pages', () => {
    it('keeps unapplied edits when leaving the Config page, and says so', async () => {
        const { fetch } = renderWithServer(<Pages />, { state: makeState() });
        fireEvent.change(await iterationsInput(), { target: { value: '25' } });
        expect(screen.getByText(/Unapplied changes: press Apply/)).toBeInTheDocument();

        fireEvent.click(screen.getByText('switch')); // to the Run page
        expect(await screen.findByText(/Config page has unapplied changes/)).toBeInTheDocument();
        expect(screen.getByText(/40 iterations/)).toBeInTheDocument(); // not applied yet

        fireEvent.click(screen.getByText('switch')); // back to Config
        expect(await iterationsInput()).toHaveValue(25);
        fireEvent.click(screen.getByRole('button', { name: 'Apply' }));
        await waitFor(() =>
            expect(
                fetch.mock.calls.some(([, init]) => (init as RequestInit)?.method === 'PUT'),
            ).toBe(true),
        );
        const put = fetch.mock.calls.find(([, init]) => (init as RequestInit)?.method === 'PUT')!;
        expect(JSON.parse(String((put[1] as RequestInit).body)).run.iterations).toBe(25);

        fireEvent.click(screen.getByText('switch')); // the Run page now shows it
        expect(await screen.findByText(/25 iterations/)).toBeInTheDocument();
        expect(screen.queryByText(/unapplied changes/)).not.toBeInTheDocument();
    });

    it('Reset discards the edits', async () => {
        renderWithServer(<Pages />, { state: makeState() });
        fireEvent.change(await iterationsInput(), { target: { value: '25' } });
        fireEvent.click(screen.getByRole('button', { name: 'Reset' }));
        expect(await iterationsInput()).toHaveValue(40);
        expect(screen.queryByText(/Unapplied changes/)).not.toBeInTheDocument();
    });
});
