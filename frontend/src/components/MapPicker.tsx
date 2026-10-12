import "leaflet/dist/leaflet.css";
import { useEffect } from "react";
import { CircleMarker, MapContainer, TileLayer, Tooltip, useMap, useMapEvents } from "react-leaflet";
import type { PresetLocation } from "../api/types";
import { formatCoordinate } from "../lib/format";

export interface MapPoint {
  latitude: number;
  longitude: number;
}

interface Props {
  locations: PresetLocation[];
  /** The point the form currently describes, if its coordinates are valid. */
  selected: MapPoint | null;
  selectedPresetId: string | null;
  /** Centre of the reanalysis grid cell matched by the last analysis, if any. */
  gridCell: MapPoint | null;
  onPickPoint: (point: MapPoint) => void;
  onPickPreset: (presetId: string) => void;
}

const INDIA_CENTRE: [number, number] = [21.5, 79];
const COLORS = { preset: "#0f5f73", selected: "#eb6834", grid: "#46525a" };

/**
 * Optional map for choosing the analysis point. Circle markers are used instead
 * of Leaflet's image markers so no icon assets have to be bundled. Every action
 * here is also possible with the Location select and the coordinate fields.
 */
export function MapPicker({
  locations,
  selected,
  selectedPresetId,
  gridCell,
  onPickPoint,
  onPickPreset,
}: Props) {
  return (
    <div>
      <div
        role="group"
        aria-label="Map for choosing the analysis point"
        className="isolate h-64 overflow-hidden rounded-md border border-line"
      >
        <MapContainer
          center={INDIA_CENTRE}
          zoom={4}
          minZoom={2}
          worldCopyJump
          scrollWheelZoom={false}
          className="h-full w-full"
        >
          <TileLayer
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            maxZoom={12}
          />
          <ClickToPick onPickPoint={onPickPoint} />
          <KeepInView point={selected} />

          {locations.map((location) => (
            <CircleMarker
              key={location.id}
              center={[location.latitude, location.longitude]}
              radius={6}
              pathOptions={{ color: "#ffffff", weight: 2, fillColor: COLORS.preset, fillOpacity: 1 }}
              eventHandlers={{ click: () => onPickPreset(location.id) }}
              // Let a click on a city select the preset rather than a custom point under it.
              bubblingMouseEvents={false}
            >
              <Tooltip direction="top" offset={[0, -6]}>
                {location.name}
              </Tooltip>
            </CircleMarker>
          ))}

          {gridCell && (
            <CircleMarker
              center={[gridCell.latitude, gridCell.longitude]}
              radius={9}
              interactive={false}
              pathOptions={{ color: COLORS.grid, weight: 2, dashArray: "3 3", fillOpacity: 0 }}
            />
          )}

          {selected && (
            <CircleMarker
              center={[selected.latitude, selected.longitude]}
              radius={8}
              interactive={false}
              pathOptions={{ color: "#ffffff", weight: 2, fillColor: COLORS.selected, fillOpacity: 1 }}
            />
          )}
        </MapContainer>
      </div>

      <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-2">
        <LegendDot color={COLORS.selected} label={selectedLabel(selected, selectedPresetId, locations)} />
        <LegendDot color={COLORS.preset} label="Preset city (click to select)" />
        {gridCell && (
          <li className="flex items-center gap-1.5">
            <span
              aria-hidden="true"
              className="inline-block h-2.5 w-2.5 rounded-full border border-dashed border-ink-2"
            />
            Matched grid cell centre of the last analysis
          </li>
        )}
      </ul>
      <p className="mt-1 text-xs text-ink-3">
        Click the map to set a custom point. The analysis uses the single reanalysis grid cell that
        contains the point, not the visible map area.
      </p>
    </div>
  );
}

function selectedLabel(
  selected: MapPoint | null,
  presetId: string | null,
  locations: PresetLocation[],
): string {
  if (!selected) return "No valid point selected";
  const preset = locations.find((location) => location.id === presetId);
  const coordinates = formatCoordinate(selected.latitude, selected.longitude);
  return preset ? `Selected: ${preset.name} (${coordinates})` : `Selected: custom point ${coordinates}`;
}

function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <li className="flex items-center gap-1.5">
      <span aria-hidden="true" className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: color }} />
      {label}
    </li>
  );
}

function ClickToPick({ onPickPoint }: { onPickPoint: (point: MapPoint) => void }) {
  useMapEvents({
    click(event) {
      // wrap() brings the longitude back into -180..180 when the world map repeats.
      const { lat, lng } = event.latlng.wrap();
      onPickPoint({ latitude: roundTo(lat, 4), longitude: roundTo(lng, 4) });
    },
  });
  return null;
}

/** Pans to the selected point when it was chosen elsewhere and is off screen. */
function KeepInView({ point }: { point: MapPoint | null }) {
  const map = useMap();
  const latitude = point?.latitude;
  const longitude = point?.longitude;
  useEffect(() => {
    if (latitude === undefined || longitude === undefined) return;
    if (!map.getBounds().contains([latitude, longitude])) {
      map.panTo([latitude, longitude]);
    }
  }, [map, latitude, longitude]);
  return null;
}

function roundTo(value: number, digits: number): number {
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
}
