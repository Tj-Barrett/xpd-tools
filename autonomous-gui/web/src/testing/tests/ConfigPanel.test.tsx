import { fireEvent, screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import ConfigPanel from '@/features/ConfigPanel';
import { makeState } from '@/stories/mocks';
import { renderWithServer } from '../renderWithServer';

describe('ConfigPanel', () => {
    it('asks for a config when none is loaded', async () => {
        renderWithServer(<ConfigPanel />, { state: makeState({ status: 'empty', config: null }) });
        expect(await screen.findByText(/No config loaded/)).toBeInTheDocument();
    });

    it('applies an edit with a PUT of the whole config', async () => {
        const { fetch } = renderWithServer(<ConfigPanel />, { state: makeState() });
        const exposure = (await screen.findByText('exposure'))
            .closest('label')!
            .querySelector('input')!;
        fireEvent.change(exposure, { target: { value: '30' } });
        fireEvent.click(screen.getByRole('button', { name: 'Apply' }));

        const put = await waitFor(() => {
            const call = fetch.mock.calls.find(
                ([, init]) => (init as RequestInit)?.method === 'PUT',
            );
            expect(call).toBeDefined();
            return call!;
        });
        expect(put[0]).toBe('/api/config');
        expect(JSON.parse(String((put[1] as RequestInit).body)).xray.settings.exposure).toBe(30);
    });

    it('locks everything but success_criteria while running', async () => {
        renderWithServer(<ConfigPanel />, {
            state: makeState({ status: 'running', editable: ['success_criteria'] }),
        });
        expect(
            await screen.findByText(/Running: only success_criteria can change/),
        ).toBeInTheDocument();
        // dds2_p1 is both a pump id and a source's pump; both are locked.
        for (const input of screen.getAllByDisplayValue('dds2_p1')) expect(input).toBeDisabled();
        const criteria = screen
            .getByText('success_criteria')
            .closest('label')!
            .querySelector('input')!;
        expect(criteria).toBeEnabled();
    });

    it('puts top-level single values in a general tile, still saved at the top level', async () => {
        const { fetch } = renderWithServer(<ConfigPanel />, { state: makeState() });
        const general = (await screen.findByText('general')).closest('details')!;
        expect(general).toContainElement(screen.getByText('evaluation_method'));

        const input = screen.getByText('pdf_mode').closest('label')!.querySelector('input')!;
        fireEvent.change(input, { target: { value: 'fit' } });
        fireEvent.click(screen.getByRole('button', { name: 'Apply' }));
        await waitFor(() =>
            expect(
                fetch.mock.calls.some(([, init]) => (init as RequestInit)?.method === 'PUT'),
            ).toBe(true),
        );
        const put = fetch.mock.calls.find(([, init]) => (init as RequestInit)?.method === 'PUT')!;
        const body = JSON.parse(String((put[1] as RequestInit).body));
        expect(body.pdf_mode).toBe('fit');
        expect(body.general).toBeUndefined();
    });

    it('shades tiles by nesting depth', async () => {
        renderWithServer(<ConfigPanel />, { state: makeState() });
        const tile = async (name: string) =>
            (await screen.findAllByText(name))[0].closest('details')!;
        expect(await tile('experiment')).toHaveClass('bg-nest-1');
        expect(await tile('sources')).toHaveClass('bg-nest-2');
        expect(await tile('dilutions')).toHaveClass('bg-nest-2');
        // experiment > sources > first source
        const firstSource = (await tile('sources')).querySelector('details')!;
        expect(firstSource).toHaveClass('bg-nest-3');
    });

    it("offers the config folder's CSVs for agent_data_path", async () => {
        const { fetch } = renderWithServer(<ConfigPanel />, {
            state: makeState(),
            csvs: ['history_a.csv', 'history_b.csv'],
        });
        const label = await screen.findByText('agent_data_path');
        const select = label.closest('label')!.querySelector('select')!;
        await waitFor(() => expect(select.options).toHaveLength(3)); // (none) + 2
        fireEvent.change(select, { target: { value: 'history_b.csv' } });
        fireEvent.click(screen.getByRole('button', { name: 'Apply' }));
        await waitFor(() =>
            expect(
                fetch.mock.calls.some(([, init]) => (init as RequestInit)?.method === 'PUT'),
            ).toBe(true),
        );
        const put = fetch.mock.calls.find(([, init]) => (init as RequestInit)?.method === 'PUT')!;
        expect(JSON.parse(String((put[1] as RequestInit).body)).agent_data_path).toBe(
            'history_b.csv',
        );
    });
});
