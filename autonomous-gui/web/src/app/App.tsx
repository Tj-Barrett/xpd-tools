import { FinchAppLayout } from '@blueskyproject/finch';
import { ChartScatter, Play, SlidersHorizontal, WaveSine } from '@phosphor-icons/react';
import ConfigPanel from '@/features/ConfigPanel';
import RunPanel from '@/features/RunPanel';
import TrialsPanel from '@/features/TrialsPanel';

export default function App() {
    return (
        <FinchAppLayout
            headerTitle="XPD Autonomous Experimentation"
            // Header icon (Phosphor, like the sidebar), in colors.ts `header.logo`.
            headerLogoIcon={<WaveSine size={40} className="text-header-logo" />}
            // Frame colours from src/theme/colors.ts; `[&>div>div]` reaches the link dividers.
            classNameHeader="bg-header"
            classNameHeaderTitle="text-header-title"
            classNameSidebar="bg-sidebar [&>div>div]:border-sidebar-divider"
            classNameSidebarInactiveLink="text-sidebar-text hover:bg-sidebar-hover"
            classNameSidebarActiveLink="bg-sidebar-active text-sidebar-active-text"
            classNameMainContent="bg-page"
            classNameMainContentInnerContainer="bg-card"
            routes={[
                { path: '/', label: 'Run', element: <RunPanel />, icon: <Play size={32} /> },
                {
                    path: '/config',
                    label: 'Config',
                    element: <ConfigPanel />,
                    icon: <SlidersHorizontal size={32} />,
                },
                {
                    path: '/trials',
                    label: 'Trials',
                    element: <TrialsPanel />,
                    icon: <ChartScatter size={32} />,
                },
            ]}
        />
    );
}
