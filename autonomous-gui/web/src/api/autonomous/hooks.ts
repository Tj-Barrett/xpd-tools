import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import * as requests from './requests';
import { Action } from './types';

/** Poll the server state every 2 s. */
export function useAppStateQuery() {
    return useQuery({
        queryKey: ['autonomous', 'state'],
        queryFn: requests.getState,
        refetchInterval: 2000,
    });
}

/** Config JSON files the server can load, newest first. */
export function useConfigsQuery() {
    return useQuery({
        queryKey: ['autonomous', 'configs'],
        queryFn: requests.getConfigs,
        refetchInterval: 5000,
    });
}

/** Historical-data CSVs in the config folder, newest first. */
export function useCsvsQuery() {
    return useQuery({
        queryKey: ['autonomous', 'csvs'],
        queryFn: requests.getCsvs,
        refetchInterval: 5000,
    });
}

/** Build / run / stop / clear / load / config, refreshing the state on success. */
export function useActionMutation() {
    const client = useQueryClient();
    return useMutation({
        mutationFn: ({ action, body }: { action: Action; body?: unknown }) =>
            requests.postAction(action, body),
        onSuccess: (state) => client.setQueryData(['autonomous', 'state'], state),
    });
}
