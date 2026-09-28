import { FinchAppLayout } from '@blueskyproject/finch';
import { ChartScatter, Play, SlidersHorizontal, RobotIcon } from '@phosphor-icons/react';
// WaveSine, Atom, RobotIcon, ChartLine,
import ConfigPanel from '@/features/ConfigPanel';
import RunPanel from '@/features/RunPanel';
import TrialsPanel from '@/features/TrialsPanel';
import { ConfigDraftProvider } from '@/hooks/useConfigDraft';

export default function App() {
    return (
        // Unapplied Config edits live here, above the routes, so switching pages keeps them.
        <ConfigDraftProvider>
            <FinchAppLayout
                headerTitle="XPD Autonomous Experimentation"
                // Header icon (Phosphor, like the sidebar), in colors.ts `header.logo`.
                headerLogoIcon={<RobotIcon size={40} className="text-header-logo" />}
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
        </ConfigDraftProvider>
    );
}
