import L from 'leaflet';

// leaflet.markercluster (UMD) membaca `L` global. Modul ini harus dievaluasi sebelum plugin.
if (typeof window !== 'undefined') window.L = L;
