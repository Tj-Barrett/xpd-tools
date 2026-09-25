import type { Meta, StoryObj } from '@storybook/react';
import ConfigPanel from '@/features/ConfigPanel';
import { makeState, makeTrials } from './mocks';
import { mockConfig } from './mockConfig';

const meta: Meta<typeof ConfigPanel> = {
    title: 'Features/ConfigPanel',
    component: ConfigPanel,
};
export default meta;
type Story = StoryObj<typeof ConfigPanel>;

export const Editable: Story = {
    parameters: { server: { state: makeState() } },
};

export const LockedWhileRunning: Story = {
    parameters: {
        server: {
            state: makeState({
                status: 'running',
                editable: ['success_criteria'],
                trials: makeTrials(5),
            }),
        },
    },
};

export const NoConfig: Story = {
    parameters: {
        server: { state: makeState({ status: 'empty', config: null, config_path: null }) },
    },
};

export const WithHistoricalData: Story = {
    parameters: {
        server: {
            state: makeState({
                config: { ...mockConfig, agent_data_path: 'agent_halide_data.csv' },
                historical: { path: '/beamline/configs/agent_halide_data.csv', count: null },
            }),
        },
    },
};
