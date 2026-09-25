import type { Meta, StoryObj } from '@storybook/react';
import LoadConfig from '@/components/LoadConfig';
import { makeState } from './mocks';

const meta: Meta<typeof LoadConfig> = {
    title: 'Components/LoadConfig',
    component: LoadConfig,
};
export default meta;
type Story = StoryObj<typeof LoadConfig>;

export const Default: Story = {
    parameters: {
        server: {
            state: makeState(),
            configs: [
                'autonomous_build_config__2026-09-25T14-02-11.json',
                'autonomous_build_config.json',
                'halide_uvvis_only.json',
            ],
        },
    },
};

export const NoConfigsFound: Story = {
    parameters: { server: { state: makeState({ status: 'empty', config: null }), configs: [] } },
};

export const WhileRunning: Story = {
    parameters: {
        server: { state: makeState({ status: 'running', editable: ['success_criteria'] }) },
    },
};
