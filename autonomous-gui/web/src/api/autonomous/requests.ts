import { Action, AppState } from './types';

/** Call server.py's /api, turning its `detail` error messages into thrown Errors. */
async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
    const response = await fetch(`/api${path}`, {
        method,
        headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!response.ok) {
        const { detail } = await response.json().catch(() => ({ detail: response.statusText }));
        throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
    }
    return response.json();
}

export function getState(): Promise<AppState> {
    return request('GET', '/state');
}

export function getConfigs(): Promise<string[]> {
    return request('GET', '/configs');
}

export function getCsvs(): Promise<string[]> {
    return request('GET', '/csvs');
}

export function postAction(action: Action, body?: unknown): Promise<AppState> {
    return action === 'config'
        ? request('PUT', '/config', body)
        : request('POST', `/${action}`, body);
}
