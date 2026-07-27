import { useEffect, useRef, useState } from 'react';
import { Input } from '../../../components/ui';
import { SEARCH_DEBOUNCE_MS } from '../wardrobe.constants';
import { useWardrobeFilterStore } from '../wardrobe.store';

// Thin wrapper around Input variant="search" with a local debounce before
// writing to useWardrobeFilterStore.setSearch -- avoids re-deriving the
// filtered array on every keystroke (design doc's Files section).
export function SearchBar() {
  const storeSearch = useWardrobeFilterStore((state) => state.search);
  const setSearch = useWardrobeFilterStore((state) => state.setSearch);
  const [text, setText] = useState(storeSearch);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }
    };
  }, []);

  const handleChangeText = (value: string) => {
    setText(value);
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
    }
    debounceRef.current = setTimeout(() => {
      setSearch(value);
    }, SEARCH_DEBOUNCE_MS);
  };

  const handleClear = () => {
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
    }
    setText('');
    setSearch('');
  };

  return (
    <Input
      variant="search"
      value={text}
      onChangeText={handleChangeText}
      onClear={handleClear}
      placeholder="Search your wardrobe"
    />
  );
}
