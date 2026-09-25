import type { Preview } from '@storybook/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router'
import '@blueskyproject/finch/style.css'
import '../src/tailwind.css'
import { mockFetch, type MockServer } from '../src/stories/mocks'

/**
 * Every story gets a fresh React Query client and a fake server.py: `fetch` is
 * swapped for one answering /api/* from the story's `parameters.server`, so the
 * real hooks and components run with no backend.
 */
const perStory = new Map<string, { client: QueryClient; fetch: typeof window.fetch }>()

const preview: Preview = {
  decorators: [
    (Story, { id, parameters }) => {
      // One client and fake server per story, kept across re-renders.
      if (!perStory.has(id)) {
        perStory.set(id, {
          client: new QueryClient({ defaultOptions: { queries: { retry: false } } }),
          fetch: mockFetch(parameters.server as MockServer | undefined),
        })
      }
      const { client, fetch } = perStory.get(id)!
      window.fetch = fetch
      return (
        <MemoryRouter>
          <QueryClientProvider client={client}>
            <Story />
          </QueryClientProvider>
        </MemoryRouter>
      )
    },
  ],
  parameters: { layout: 'padded' },
}

export default preview
