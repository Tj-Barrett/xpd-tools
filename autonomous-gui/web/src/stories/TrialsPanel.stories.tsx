import type { Meta, StoryObj } from '@storybook/react';
import TrialsPanel from '@/features/TrialsPanel';
import { makeState, makeTrials } from './mocks';

const meta: Meta<typeof TrialsPanel> = {
    title: 'Features/TrialsPanel',
    component: TrialsPanel,
};
export default meta;
type Story = StoryObj<typeof TrialsPanel>;

export const NoTrials: Story = {
    parameters: { server: { state: makeState() } },
};

export const FewTrials: Story = {
    parameters: { server: { state: makeState({ status: 'running', trials: makeTrials(5) }) } },
};

export const FinishedCampaign: Story = {
    parameters: { server: { state: makeState({ status: 'finished', trials: makeTrials(40) }) } },
};

export const StoppedWithFailedTrial: Story = {
    parameters: {
        server: {
            state: makeState({ status: 'stopped', trials: makeTrials(13, { lastFailed: true }) }),
        },
    },
};

export const WithHistoricalData: Story = {
    parameters: {
        server: {
            state: makeState({
                status: 'running',
                trials: makeTrials(20),
                historical: { path: '/beamline/configs/agent_halide_data.csv', count: 12 },
            }),
        },
    },
};
