"use client";

import { createContext, useCallback, useContext, useEffect, useState, ReactNode } from "react";

const STORAGE_KEY = "patentologos:search";

type SearchState = {
  query: string;
  page: number;
};

type SearchContextValue = SearchState & {
  setSearch: (next: SearchState) => void;
  clearSearch: () => void;
  hasSearch: boolean;
  buildHref: () => string;
};

const SearchContext = createContext<SearchContextValue | null>(null);

const EMPTY: SearchState = { query: "", page: 1 };

export function SearchProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<SearchState>(EMPTY);

  useEffect(() => {
    try {
      const raw = sessionStorage.getItem(STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw) as SearchState;
        if (typeof parsed.query === "string" && typeof parsed.page === "number") {
          setState(parsed);
        }
      }
    } catch {
      // ignore
    }
  }, []);

  const setSearch = useCallback((next: SearchState) => {
    setState((prev) => {
      if (prev.query === next.query && prev.page === next.page) return prev;
      try {
        sessionStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      } catch {
        // ignore
      }
      return next;
    });
  }, []);

  const clearSearch = useCallback(() => {
    setState(EMPTY);
    try {
      sessionStorage.removeItem(STORAGE_KEY);
    } catch {
      // ignore
    }
  }, []);

  function buildHref() {
    const params = new URLSearchParams();
    if (state.query.trim()) params.set("q", state.query.trim());
    if (state.page > 1) params.set("page", String(state.page));
    const qs = params.toString();
    return qs ? `/?${qs}` : "/";
  }

  const hasSearch = state.query.trim().length > 0;

  return (
    <SearchContext.Provider value={{ ...state, setSearch, clearSearch, hasSearch, buildHref }}>
      {children}
    </SearchContext.Provider>
  );
}

export function useSearch() {
  const ctx = useContext(SearchContext);
  if (!ctx) throw new Error("useSearch must be used within SearchProvider");
  return ctx;
}
