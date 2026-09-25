/** Response of server.py's GET /api/state (and of every action). */
export type AppState = {
    status:
        'empty' | 'loaded' | 'built' | 'running' | 'stopping' | 'finished' | 'stopped' | 'failed';
    error: string | null;
    mode: 'queue_server' | 'local' | null;
    config_dir: string;
    config_path: string | null;
    config: Record<string, any> | null;
    editable: 'all' | string[];
    trials: Record<string, any>[];
    trials_path: string | null;
    /** agent_data_path resolved to a file, and how many rows were ingested at Build. */
    historical: { path: string | null; count: number | null };
};

/** Actions the GUI can ask server.py for; 'config' is PUT /api/config, the rest POST. */
export type Action = 'build' | 'run' | 'stop' | 'config' | 'load' | 'clear';
