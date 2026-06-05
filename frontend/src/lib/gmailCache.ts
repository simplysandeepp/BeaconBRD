import { useAuthStore } from "@/store/useAuthStore";
import type { GmailEmail } from "./apiClient";

export interface CachedGmailData {
    emails: GmailEmail[];
    nextPageToken: string | null;
}

const gmailMemoryCache: { [key: string]: CachedGmailData } = {};

function getCacheKey(key: string): string | null {
    const uid = useAuthStore.getState().user?.uid;
    if (!uid) return null;
    return `${uid}:${key}`;
}

export function getGmailCache(key: string): CachedGmailData | null {
    const cacheKey = getCacheKey(key);
    if (!cacheKey) return null;
    return gmailMemoryCache[cacheKey] || null;
}

export function setGmailCache(key: string, data: CachedGmailData) {
    const cacheKey = getCacheKey(key);
    if (!cacheKey) return;
    gmailMemoryCache[cacheKey] = data;
}

export function clearGmailCache() {
    const uid = useAuthStore.getState().user?.uid;
    if (!uid) return;
    for (const key in gmailMemoryCache) {
        if (key.startsWith(`${uid}:`)) {
            delete gmailMemoryCache[key];
        }
    }
}
