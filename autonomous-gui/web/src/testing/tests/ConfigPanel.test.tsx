import { fireEvent, screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import ConfigPanel from '@/features/ConfigPanel';
import { makeState } from '@/stories/mocks';
import { mockConfig } from '@/stories/mockConfig';
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
            .querySelector('select')!;
        expect(criteria).toBeEnabled();
    });

    it('puts top-level single values in a general tile, still saved at the top level', async () => {
        const { fetch } = renderWithServer(<ConfigPanel />, { state: makeState() });
        const general = (await screen.findByText('general')).closest('details')!;
        expect(general).toContainElement(screen.getByText('evaluation_method'));

        const input = screen.getByText('pdf_mode').closest('label')!.querySelector('select')!;
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

    it('hides n_points but still sends it as 1', async () => {
        const { fetch } = renderWithServer(<ConfigPanel />, { state: makeState() });
        const iterations = (await screen.findByText('iterations'))
            .closest('label')!
            .querySelector('input')!;
        expect(screen.queryByText('n_points')).not.toBeInTheDocument();
        fireEvent.change(iterations, { target: { value: '12' } });
        fireEvent.click(screen.getByRole('button', { name: 'Apply' }));
        await waitFor(() =>
            expect(
                fetch.mock.calls.some(([, init]) => (init as RequestInit)?.method === 'PUT'),
            ).toBe(true),
        );
        const put = fetch.mock.calls.find(([, init]) => (init as RequestInit)?.method === 'PUT')!;
        expect(JSON.parse(String((put[1] as RequestInit).body)).run).toMatchObject({
            iterations: 12,
            n_points: 1,
        });
    });

    it("hides the pumps' target volume but keeps it in the config", async () => {
        const { fetch } = renderWithServer(<ConfigPanel />, { state: makeState() });
        await screen.findByText('iterations');
        expect(screen.getAllByText('precursor').length).toBeGreaterThan(0); // pumps shown
        expect(screen.queryByText('target_ml')).not.toBeInTheDocument();
        expect(screen.queryByText('set_target')).not.toBeInTheDocument();
        fireEvent.change(screen.getByText('iterations').closest('label')!.querySelector('input')!, {
            target: { value: '12' },
        });
        fireEvent.click(screen.getByRole('button', { name: 'Apply' }));
        await waitFor(() =>
            expect(
                fetch.mock.calls.some(([, init]) => (init as RequestInit)?.method === 'PUT'),
            ).toBe(true),
        );
        const put = fetch.mock.calls.find(([, init]) => (init as RequestInit)?.method === 'PUT')!;
        const sent = JSON.parse(String((put[1] as RequestInit).body));
        expect(sent.experiment.sources[0]).toMatchObject({ target_ml: 30, set_target: true });
    });

    it('offers the supported objective functions in a dropdown', async () => {
        const { fetch } = renderWithServer(<ConfigPanel />, { state: makeState() });
        const select = (await screen.findByText('objective_function'))
            .closest('label')!
            .querySelector('select')!;
        const options = [...select.options].map((option) => option.value);
        expect(options).toEqual([
            'cnn',
            'cross_correlation',
            'ensemble',
            'nn_matrix',
            'pearson',
            'weighted_profile_r',
        ]); // no "(none)": it's required
        fireEvent.change(select, { target: { value: 'ensemble' } });
        fireEvent.click(screen.getByRole('button', { name: 'Apply' }));
        await waitFor(() =>
            expect(
                fetch.mock.calls.some(([, init]) => (init as RequestInit)?.method === 'PUT'),
            ).toBe(true),
        );
        const put = fetch.mock.calls.find(([, init]) => (init as RequestInit)?.method === 'PUT')!;
        expect(JSON.parse(String((put[1] as RequestInit).body)).xray.objective_function).toBe(
            'ensemble',
        );
    });

    it.each([
        ['evaluation_method', ['uvvis', 'xray', 'xray-uvvis']],
        ['pdf_mode', ['raw', 'fit', 'raw_tracked']],
    ])('offers %s in a dropdown', async (field, options) => {
        renderWithServer(<ConfigPanel />, { state: makeState() });
        const select = (await screen.findByText(field)).closest('label')!.querySelector('select')!;
        expect([...select.options].map((option) => option.value)).toEqual(options);
    });

    it('offers the screening modes in a dropdown', async () => {
        renderWithServer(<ConfigPanel />, { state: makeState() });
        const select = (await screen.findByText('screening'))
            .closest('label')!
            .querySelector('select')!;
        expect([...select.options].map((option) => option.value)).toEqual([
            'unscreened',
            'screen_only',
            'screen_and_record',
        ]);
    });

    it("lists a group's single values before its sub-tiles", async () => {
        renderWithServer(<ConfigPanel />, { state: makeState() });
        await screen.findByText('objective_function');
        // In document order, every loose xray field comes before the settings tile.
        const order = (text: string) => screen.getByText(text);
        const settings = order('settings');
        for (const field of ['screening', 'objective_function', 'min_radius']) {
            expect(
                order(field).compareDocumentPosition(settings) & Node.DOCUMENT_POSITION_FOLLOWING,
            ).toBeTruthy();
        }
    });

    it('picks the simulation from a dropdown, then a DOF per phase', async () => {
        const { fetch } = renderWithServer(<ConfigPanel />, { state: makeState() });
        const select = () =>
            screen.getByText('simulated').closest('label')!.querySelector('select')!;
        await screen.findByText('simulated');
        expect(select().selectedOptions[0].text).toBe('Fake data (echoes the reference PDFs)');
        expect(screen.queryByText('dof_for_phase')).not.toBeInTheDocument();

        fireEvent.change(select(), { target: { value: '1' } });
        expect(select().selectedOptions[0].text).toBe('Materials Project simulation');
        const dof = screen.getByText('CsPbBr3', { selector: 'span' }).closest('label')!;
        fireEvent.change(dof.querySelector('select')!, { target: { value: 'infusion_rate_Br' } });
        fireEvent.click(screen.getByRole('button', { name: 'Apply' }));
        await waitFor(() =>
            expect(
                fetch.mock.calls.some(([, init]) => (init as RequestInit)?.method === 'PUT'),
            ).toBe(true),
        );
        const put = fetch.mock.calls.find(([, init]) => (init as RequestInit)?.method === 'PUT')!;
        expect(JSON.parse(String((put[1] as RequestInit).body)).run.local.simulated).toEqual({
            dof_for_phase: { CsPbBr3: 'infusion_rate_Br' },
        });
    });

    it('picks a success criterion, then shows only its number boxes', async () => {
        const { fetch } = renderWithServer(<ConfigPanel />, { state: makeState() });
        const select = () =>
            screen.getByText('success_criteria').closest('label')!.querySelector('select')!;
        await screen.findByText('success_criteria');
        expect(select().selectedOptions[0].text).toBe('None (runs all iterations)');

        fireEvent.change(select(), { target: { value: '2' } });
        expect(select().selectedOptions[0].text).toBe('Maximum FWHM and minimum PLQY');
        expect(screen.queryByText('min_correlation')).toBeNull();
        const box = (field: string) =>
            screen.getByText(field).closest('label')!.querySelector('input')!;
        fireEvent.change(box('max_fwhm'), { target: { value: '25' } });
        fireEvent.change(box('min_plqy'), { target: { value: '0.4' } });
        fireEvent.click(screen.getByRole('button', { name: 'Apply' }));
        await waitFor(() =>
            expect(
                fetch.mock.calls.some(([, init]) => (init as RequestInit)?.method === 'PUT'),
            ).toBe(true),
        );
        const put = fetch.mock.calls.find(([, init]) => (init as RequestInit)?.method === 'PUT')!;
        expect(JSON.parse(String((put[1] as RequestInit).body)).success_criteria).toEqual({
            max_fwhm: 25,
            min_plqy: 0.4,
            poll_interval: 5,
        });
    });

    it("shows a saved criterion's option and hides the other option's empty fields", async () => {
        renderWithServer(<ConfigPanel />, {
            state: makeState({
                config: {
                    ...mockConfig,
                    // as to_config() writes it: every field, unused ones null
                    success_criteria: {
                        min_correlation: 0.8,
                        max_fwhm: null,
                        min_plqy: null,
                        poll_interval: 5,
                    },
                },
            }),
        });
        const select = (await screen.findByText('success_criteria'))
            .closest('label')!
            .querySelector('select')!;
        expect(select.selectedOptions[0].text).toBe('Minimum correlation');
        expect(screen.getByDisplayValue('0.8')).toBeInTheDocument();
        expect(screen.queryByText('max_fwhm')).toBeNull();
    });

    it('keeps a picked preset and its settings where the dropdown was', async () => {
        renderWithServer(<ConfigPanel />, { state: makeState() });
        const general = (await screen.findByText('general')).closest('details')!;
        const dropdown = (name: string) =>
            screen.getByText(name).closest('label')!.querySelector('select')!;
        const after = (a: Element, b: Element) =>
            !!(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);

        fireEvent.change(dropdown('success_criteria'), { target: { value: '1' } });
        // Still in general, with its settings box nested there right below it.
        expect(general).toContainElement(dropdown('success_criteria'));
        expect(general).toContainElement(screen.getByText('min_correlation'));
        expect(after(dropdown('success_criteria'), screen.getByText('min_correlation'))).toBe(true);

        // run.local.simulated likewise keeps its place among run.local's fields.
        fireEvent.change(dropdown('simulated'), { target: { value: '1' } });
        expect(after(dropdown('simulated'), screen.getByText('skip_waits'))).toBe(true);
    });
});
