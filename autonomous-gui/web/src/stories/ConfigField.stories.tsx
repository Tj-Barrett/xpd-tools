import type { Meta, StoryObj } from '@storybook/react';
import ConfigField from '@/components/ConfigField';
import { mockConfig } from './mockConfig';

// ConfigField takes plain props, so these stories use args (editable in the Controls panel).
const meta: Meta<typeof ConfigField> = {
    title: 'Components/ConfigField',
    component: ConfigField,
    args: { path: [], disabled: false },
    argTypes: { onChange: { action: 'changed' } },
};
export default meta;
type Story = StoryObj<typeof ConfigField>;

export const NumberValue: Story = { args: { name: 'exposure', value: 600 } };

export const TextValue: Story = { args: { name: 'tiled_profile', value: 'xpd' } };

export const NullValue: Story = { args: { name: 'agent_data_path', value: null } };

export const BooleanValue: Story = { args: { name: 'no_dark', value: false } };

export const Bounds: Story = { args: { name: 'bounds', value: [10, 200] } };

export const Group: Story = { args: { name: 'pumps', value: mockConfig.pumps } };

export const LockedGroup: Story = {
    args: { name: 'pumps', value: mockConfig.pumps, disabled: true },
};
