import { useQuery, type UseQueryResult } from '@tanstack/react-query';
import { apiGet } from './api-client';

// Shared React-Query hooks wrapping api-client. Any page can call these
// directly; caching is shared via the QueryClient in main.tsx.

export function useApiGet<T>(
  key: readonly unknown[],
  path: string,
  params?: Record<string, unknown>,
  options?: { enabled?: boolean },
): UseQueryResult<T, Error> {
  return useQuery<T, Error>({
    queryKey: [path, params, ...key],
    queryFn: async () => {
      const [data] = await apiGet<T>(path, params);
      return data;
    },
    enabled: options?.enabled ?? true,
  });
}
