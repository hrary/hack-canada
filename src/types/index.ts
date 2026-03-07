export interface SupplyPoint {
  id: string;
  name: string;
  lat: number;
  lng: number;
  material: string;
  supplier: string;
  country: string;
}

export interface SupplyArc {
  startLat: number;
  startLng: number;
  endLat: number;
  endLng: number;
  color: [string, string];
}

export interface User {
  email: string;
  name: string;
  company: string;
}
