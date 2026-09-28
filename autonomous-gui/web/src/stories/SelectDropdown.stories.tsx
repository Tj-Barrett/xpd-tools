import type { Meta, StoryObj } from '@storybook/react';
import { Button, SelectDropdown } from '@/components/themed';

const LONG =
    'autonomous_build_config_halide_CsPbBr3_high_flow_rate_screening__2026-09-28T09-14-55.json';

// The themed dropdown in the same w-80 box LoadConfig uses, next to a button.
const meta: Meta<typeof SelectDropdown> = {
    title: 'Components/SelectDropdown',
    component: SelectDropdown,
    render: (args) => (
        <div className="flex items-center gap-3">
            <div className="w-80" data-testid="box">
                <SelectDropdown {...args} />
            </div>
            <Button text="Load" size="small" />
        </div>
    ),
    args: { listItems: [LONG, 'short.json'], placeholder: 'Choose a config…' },
};
export default meta;
type Story = StoryObj<typeof SelectDropdown>;

export const Placeholder: Story = {};

export const LongSelection: Story = { args: { initialSelectedItem: LONG } };

export const ShortSelection: Story = { args: { initialSelectedItem: 'short.json' } };
