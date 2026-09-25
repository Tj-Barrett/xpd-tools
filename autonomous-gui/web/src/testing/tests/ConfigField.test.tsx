import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import ConfigField from '@/components/ConfigField';

describe('ConfigField', () => {
    it('renders a number as a number input and reports edits as numbers', () => {
        const onChange = vi.fn();
        render(
            <ConfigField
                name="exposure"
                value={600}
                path={['xray', 'exposure']}
                disabled={false}
                onChange={onChange}
            />,
        );
        const input = screen.getByRole('spinbutton');
        expect(input).toHaveValue(600);
        fireEvent.change(input, { target: { value: '5' } });
        expect(onChange).toHaveBeenCalledWith(['xray', 'exposure'], 5);
    });

    it('parses a null field as JSON so numbers stay numbers', () => {
        const onChange = vi.fn();
        render(
            <ConfigField
                name="min_correlation"
                value={null}
                path={['c']}
                disabled={false}
                onChange={onChange}
            />,
        );
        fireEvent.change(screen.getByPlaceholderText('null'), { target: { value: '0.9' } });
        expect(onChange).toHaveBeenCalledWith(['c'], 0.9);
    });

    it('keeps a string field a string', () => {
        const onChange = vi.fn();
        render(
            <ConfigField
                name="tiled_profile"
                value="xpd"
                path={['p']}
                disabled={false}
                onChange={onChange}
            />,
        );
        fireEvent.change(screen.getByRole('textbox'), { target: { value: '123' } });
        expect(onChange).toHaveBeenCalledWith(['p'], '123');
    });

    it('edits one item of a bounds pair by index', () => {
        const onChange = vi.fn();
        render(
            <ConfigField
                name="bounds"
                value={[10, 200]}
                path={['pumps', 0, 'bounds']}
                disabled={false}
                onChange={onChange}
            />,
        );
        const [, high] = screen.getAllByRole('spinbutton');
        fireEvent.change(high, { target: { value: '150' } });
        expect(onChange).toHaveBeenCalledWith(['pumps', 0, 'bounds', 1], 150);
    });

    it('renders a collapsible group, named by each item', () => {
        render(
            <ConfigField
                name="pumps"
                value={[
                    { name: 'CsPb', id: 'dds2_p1' },
                    { name: 'Br', id: 'dds2_p2' },
                ]}
                path={['pumps']}
                disabled={false}
                onChange={vi.fn()}
            />,
        );
        expect(screen.getByText('pumps').tagName).toBe('SUMMARY');
        expect(screen.getByText('CsPb').tagName).toBe('SUMMARY');
        expect(screen.getByDisplayValue('dds2_p2')).toBeInTheDocument();
    });

    it('disables every input in a locked group', () => {
        render(
            <ConfigField
                name="settings"
                value={{ exposure: 5, stream_name: 'scattering' }}
                path={['s']}
                disabled
                onChange={vi.fn()}
            />,
        );
        expect(screen.getByRole('spinbutton')).toBeDisabled();
        expect(screen.getByRole('textbox')).toBeDisabled();
    });
});
