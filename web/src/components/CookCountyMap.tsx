"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import gsap from "gsap";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const TYPE_COLORS: Record<string, string> = {
  township: "#3b82f6",
  municipality: "#10b981",
  county: "#8b5cf6",
  special_district: "#f59e0b",
};

const COOK_CENTER: L.LatLngExpression = [41.84, -87.82];

interface FeatureProps {
  id: string;
  name: string;
  unit_type: string;
  population: number | null;
  latest_fy: number | null;
  officials_count: number;
}

interface Props {
  filterType?: string;
  className?: string;
  compact?: boolean;
}

export default function CookCountyMap({
  filterType,
  className = "",
  compact = false,
}: Props) {
  const [loading, setLoading] = useState(true);
  const mapRef = useRef<L.Map | null>(null);
  const geoLayerRef = useRef<L.GeoJSON | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const mapElRef = useRef<HTMLDivElement>(null);
  const router = useRouter();

  // Initialize map once
  useEffect(() => {
    if (!mapElRef.current || mapRef.current) return;

    const map = L.map(mapElRef.current, {
      center: COOK_CENTER,
      zoom: 10,
      minZoom: 9,
      maxZoom: 14,
      scrollWheelZoom: true,
      zoomControl: true,
    });

    L.tileLayer(
      "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
      {
        attribution: '&copy; <a href="https://carto.com">CARTO</a>',
      }
    ).addTo(map);

    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // Load GeoJSON when filterType changes
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    setLoading(true);

    // Remove old layer
    if (geoLayerRef.current) {
      map.removeLayer(geoLayerRef.current);
      geoLayerRef.current = null;
    }

    const url = filterType
      ? `${API_BASE}/units/geojson?type=${filterType}`
      : `${API_BASE}/units/geojson`;

    fetch(url)
      .then((r) => r.json())
      .then((data) => {
        if (!data.features || data.features.length === 0) {
          setLoading(false);
          return;
        }

        const layer = L.geoJSON(data, {
          style: (feature) => {
            const unitType = feature?.properties?.unit_type || "";
            const color = TYPE_COLORS[unitType] || "#6b7280";
            return {
              fillColor: color,
              fillOpacity: 0.3,
              color: color,
              weight: 1.5,
              opacity: 0.7,
            };
          },
          onEachFeature: (feature, featureLayer) => {
            const props = feature.properties as FeatureProps;
            const baseColor = TYPE_COLORS[props.unit_type] || "#6b7280";

            featureLayer.on({
              mouseover: () => {
                (featureLayer as L.Path).setStyle({
                  fillOpacity: 0.55,
                  weight: 3,
                  color: "#1e293b",
                  opacity: 1,
                });
                (featureLayer as L.Path).bringToFront();
              },
              mouseout: () => {
                (featureLayer as L.Path).setStyle({
                  fillOpacity: 0.3,
                  weight: 1.5,
                  color: baseColor,
                  opacity: 0.7,
                });
              },
              click: () => {
                router.push(`/unit/${props.id}`);
              },
            });

            const popStr = props.population
              ? `<div style="font-size:11px;color:#6b7280">Pop. ${props.population.toLocaleString()}</div>`
              : "";
            featureLayer.bindTooltip(
              `<div style="font-weight:600;font-size:13px;margin-bottom:2px">${props.name}</div>
               <div style="font-size:11px;color:#6b7280;text-transform:capitalize;margin-bottom:1px">${props.unit_type.replace("_", " ")}</div>
               ${popStr}`,
              {
                sticky: true,
                direction: "top",
                className: "civiclens-tooltip",
                offset: [0, -8],
              }
            );
          },
        }).addTo(map);

        geoLayerRef.current = layer;

        const bounds = layer.getBounds();
        if (bounds.isValid()) {
          map.fitBounds(bounds, { padding: [30, 30], animate: true });
        }

        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [filterType, router]);

  // GSAP entrance
  useEffect(() => {
    if (!containerRef.current || loading) return;
    gsap.fromTo(
      containerRef.current,
      { opacity: 0, scale: 0.97 },
      { opacity: 1, scale: 1, duration: 0.8, ease: "power2.out" }
    );
  }, [loading]);

  return (
    <div ref={containerRef} className={`opacity-0 ${className}`}>
      <div
        className={`rounded-xl overflow-hidden border border-border shadow-sm relative ${compact ? "h-64" : "h-[500px]"}`}
      >
        <div
          ref={mapElRef}
          className="h-full w-full"
          style={{ background: "#f1f5f9" }}
        />
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center bg-card/80 z-[1000]">
            <div className="flex flex-col items-center gap-3">
              <div className="w-8 h-8 border-2 border-accent border-t-transparent rounded-full animate-spin" />
              <span className="text-sm text-muted">Loading map...</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
