import { createContext, useContext, useState, type ReactNode } from 'react';
import type { User, SupplyPoint } from '../types';

interface AppContextType {
  user: User | null;
  setUser: (user: User | null) => void;
  supplyPoints: SupplyPoint[];
  setSupplyPoints: (points: SupplyPoint[]) => void;
  headquartersLocation: { lat: number; lng: number } | null;
  setHeadquartersLocation: (loc: { lat: number; lng: number } | null) => void;
}

const AppContext = createContext<AppContextType | undefined>(undefined);

export function AppProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [supplyPoints, setSupplyPoints] = useState<SupplyPoint[]>([]);
  const [headquartersLocation, setHeadquartersLocation] = useState<{ lat: number; lng: number } | null>(null);

  return (
    <AppContext.Provider value={{
      user, setUser,
      supplyPoints, setSupplyPoints,
      headquartersLocation, setHeadquartersLocation,
    }}>
      {children}
    </AppContext.Provider>
  );
}

export function useAppContext() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useAppContext must be used within AppProvider');
  return ctx;
}
