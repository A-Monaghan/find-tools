import { useState, useEffect } from 'react';

/** Matches window.matchMedia — for responsive layout (e.g. citation rail vs overlay). */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() =>
    typeof window !== 'undefined' ? window.matchMedia(query).matches : false
  );

  useEffect(() => {
    const m = window.matchMedia(query);
    const onChange = () => setMatches(m.matches);
    m.addEventListener('change', onChange);
    setMatches(m.matches);
    return () => m.removeEventListener('change', onChange);
  }, [query]);

  return matches;
}
