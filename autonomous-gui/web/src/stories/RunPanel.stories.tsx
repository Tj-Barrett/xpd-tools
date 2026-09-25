import type { Meta, StoryObj } from '@storybook/react';
import RunPanel from '@/features/RunPanel';
import { makeState, makeTrials } from './mocks';

const meta: Meta<typeof RunPanel> = {
    title: 'Features/RunPanel',
    component: RunPanel,
};
export default meta;
type Story = StoryObj<typeof RunPanel>;

const TRIALS_CSV = '/beamline/configs/autonomous_build_config__2026-09-25T14-02-11_trials.csv';

export const Empty: Story = {
    parameters: {
        server: { state: makeState({ status: 'empty', config: null, config_path: null }) },
    },
};

export const Loaded: Story = {
    parameters: { server: { state: makeState() } },
};

export const Built: Story = {
    parameters: { server: { state: makeState({ status: 'built' }) } },
};

export const Running: Story = {
    parameters: {
        server: {
            state: makeState({
                status: 'running',
                editable: ['success_criteria'],
                trials: makeTrials(12),
            }),
        },
    },
};

export const Stopping: Story = {
    parameters: {
        server: {
            state: makeState({
                status: 'stopping',
                editable: ['success_criteria'],
                trials: makeTrials(12),
            }),
        },
    },
};

export const Stopped: Story = {
    parameters: {
        server: {
            state: makeState({
                status: 'stopped',
                trials: makeTrials(13, { lastFailed: true }),
                trials_path: TRIALS_CSV,
            }),
        },
    },
};

export const Failed: Story = {
    parameters: {
        server: {
            state: makeState({
                status: 'failed',
                error: "ConnectionError('HTTP server https://xf28id2-xpd-qs1.nsls2.bnl.gov is unreachable')",
                trials: makeTrials(4),
                trials_path: TRIALS_CSV,
            }),
        },
    },
};

export const Offline: Story = {
    parameters: { server: { state: makeState(), offline: true } },
};

export const WithHistoricalData: Story = {
    parameters: {
        server: {
            state: makeState({
                status: 'running',
                editable: ['success_criteria'],
                trials: makeTrials(20),
                historical: { path: '/beamline/configs/agent_halide_data.csv', count: 12 },
            }),
        },
    },
};
