"use client";

import { useEffect, useRef, useCallback } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

const COOK_CENTER: L.LatLngExpression = [41.84, -87.82];

const STYLE_DEFAULT = {
  fillColor: "#3b82f6",
  fillOpacity: 0.15,
  color: "#3b82f6",
  weight: 1,
  opacity: 0.5,
};

const STYLE_HOVER = {
  fillColor: "#3b82f6",
  fillOpacity: 0.35,
  color: "#1e40af",
  weight: 2,
  opacity: 0.8,
};

const STYLE_SELECTED = {
  fillColor: "#c41e2a",
  fillOpacity: 0.45,
  color: "#991b1b",
  weight: 2.5,
  opacity: 1,
};

interface Props {
  geojson: any;
  selectedId: string | null;
  hoveredId: string | null;
  onSelect: (id: string | null) => void;
  onHover: (id: string | null) => void;
}

export default function CompareMap({
  geojson,
  selectedId,
  hoveredId,
  onSelect,
  onHover,
}: Props) {
  const mapRef = useRef<L.Map | null>(null);
  const layerRef = useRef<L.GeoJSON | null>(null);
  const mapElRef = useRef<HTMLDivElement>(null);
  const featureLayersRef = useRef<Map<string, L.Path>>(new Map());

  // Stable callback refs
  const onSelectRef = useRef(onSelect);
  const onHoverRef = useRef(onHover);
  onSelectRef.current = onSelect;
  onHoverRef.current = onHover;

  // Init map
  useEffect(() => {
    if (!mapElRef.current || mapRef.current) return;

    const map = L.map(mapElRef.current, {
      center: COOK_CENTER,
      zoom: 10,
      minZoom: 9,
      maxZoom: 15,
      scrollWheelZoom: true,
      zoomControl: true,
    });

    L.tileLayer(
      "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
      {
        attribution:
          '&copy; <a href="https://carto.com">CARTO</a> | <a href="https://leafletjs.com">Leaflet</a>',
      }
    ).addTo(map);

    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // Load GeoJSON
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !geojson) return;

    if (layerRef.current) {
      map.removeLayer(layerRef.current);
      layerRef.current = null;
    }
    featureLayersRef.current.clear();

    const layer = L.geoJSON(geojson, {
      style: () => ({ ...STYLE_DEFAULT }),
      onEachFeature: (feature, featureLayer) => {
        const props = feature.properties;
        const id = props.id;

        featureLayersRef.current.set(id, featureLayer as L.Path);

        featureLayer.on({
          mouseover: () => {
            onHoverRef.current(id);
          },
          mouseout: () => {
            onHoverRef.current(null);
          },
          click: () => {
            onSelectRef.current(id);
          },
        });

        const officialLine = props.official_name
          ? `<div style="font-size:12px;margin-top:2px">${props.official_role ? `<span style="text-transform:capitalize;color:#6b7280">${props.official_role}:</span> ` : ""}${props.official_name}</div>`
          : "";

        featureLayer.bindTooltip(
          `<div style="font-weight:600;font-size:13px">${props.name}</div>${officialLine}`,
          {
            sticky: true,
            direction: "top",
            className: "civiclens-tooltip",
            offset: [0, -8],
          }
        );
      },
    }).addTo(map);

    layerRef.current = layer;

    const bounds = layer.getBounds();
    if (bounds.isValid()) {
      map.fitBounds(bounds, { padding: [30, 30], animate: true });
    }
  }, [geojson]);

  // Update styles when selection/hover changes
  useEffect(() => {
    featureLayersRef.current.forEach((layer, id) => {
      if (id === selectedId) {
        layer.setStyle(STYLE_SELECTED);
        layer.bringToFront();
      } else if (id === hoveredId) {
        layer.setStyle(STYLE_HOVER);
        layer.bringToFront();
      } else {
        layer.setStyle(STYLE_DEFAULT);
      }
    });

    // Pan to selected
    if (selectedId) {
      const layer = featureLayersRef.current.get(selectedId);
      if (layer && mapRef.current) {
        const bounds = (layer as any).getBounds?.();
        if (bounds?.isValid()) {
          mapRef.current.fitBounds(bounds, {
            padding: [60, 60],
            maxZoom: 13,
            animate: true,
          });
        }
      }
    }
  }, [selectedId, hoveredId]);

  return (
    <div
      ref={mapElRef}
      className="h-full w-full"
      style={{ background: "#f1f5f9" }}
    />
  );
}
