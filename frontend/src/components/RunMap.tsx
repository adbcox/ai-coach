import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { useEffect, useRef } from "react";

interface Props {
  lat: (number | null)[];
  lon: (number | null)[];
  hoverIndex: number | null;
}

/** Route on an OpenStreetMap base layer (tiles load from the viewer's browser). */
export default function RunMap({ lat, lon, hoverIndex }: Props) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const marker = useRef<L.CircleMarker | null>(null);

  useEffect(() => {
    if (!el.current) return;
    const pts: L.LatLngTuple[] = [];
    lat.forEach((la, i) => {
      const lo = lon[i];
      if (la != null && lo != null) pts.push([la, lo]);
    });
    const m = L.map(el.current, { zoomControl: true, attributionControl: true });
    map.current = m;
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(m);
    if (pts.length > 1) {
      const line = L.polyline(pts, { color: "#1f6feb", weight: 4 }).addTo(m);
      m.fitBounds(line.getBounds(), { padding: [20, 20] });
      L.circleMarker(pts[0], { radius: 6, color: "#2da44e", fillOpacity: 1 }).addTo(m);
      L.circleMarker(pts[pts.length - 1], { radius: 6, color: "#cf222e", fillOpacity: 1 }).addTo(m);
    } else {
      m.setView([0, 0], 2);
    }
    marker.current = L.circleMarker([0, 0], { radius: 8, color: "#fff", weight: 2, fillColor: "#f59e0b", fillOpacity: 1 });
    return () => {
      m.remove();
      map.current = null;
      marker.current = null;
    };
  }, [lat, lon]);

  useEffect(() => {
    const m = map.current, mk = marker.current;
    if (!m || !mk) return;
    const la = hoverIndex == null ? null : lat[hoverIndex];
    const lo = hoverIndex == null ? null : lon[hoverIndex];
    if (la != null && lo != null) {
      mk.setLatLng([la, lo]);
      if (!m.hasLayer(mk)) mk.addTo(m);
    } else if (m.hasLayer(mk)) {
      m.removeLayer(mk);
    }
  }, [hoverIndex, lat, lon]);

  return <div ref={el} className="map" />;
}
