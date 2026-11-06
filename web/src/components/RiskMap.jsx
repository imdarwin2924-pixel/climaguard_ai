// E2-S1: district map coloured by level, with text labels; click opens the district (E3-S1).
import L from 'leaflet'
import { useMemo } from 'react'
import { GeoJSON, MapContainer } from 'react-leaflet'
import { LEVEL_COLOR } from '../api'

export default function RiskMap({ geo, districts, selectedId, onSelect, showLabels }) {
  const byName = Object.fromEntries(districts.map((d) => [d.name, d]))
  const bounds = useMemo(() => L.geoJSON(geo).getBounds(), [geo])  // whole state at any screen width

  const style = (feature) => {
    const d = byName[feature.properties.dtname.trim()]
    return {
      fillColor: d ? LEVEL_COLOR[d.level] : '#eee',
      fillOpacity: 0.9,
      color: d && d.id === selectedId ? '#111' : '#555',
      weight: d && d.id === selectedId ? 3 : 0.8,
    }
  }

  const onEachFeature = (feature, layer) => {
    const d = byName[feature.properties.dtname.trim()]
    if (!d) return
    layer.bindTooltip(showLabels ? `${d.name}<br><b>${d.level}</b>` : `${d.name}: ${d.level}`, {
      permanent: showLabels, direction: 'center', className: showLabels ? 'map-label' : '',
    })
    layer.on({ click: () => onSelect(d.id) })
  }

  return (
    <MapContainer bounds={bounds} boundsOptions={{ padding: [8, 8] }} zoomSnap={0.25} minZoom={6} maxZoom={10} scrollWheelZoom
                  className="map" attributionControl={false}>
      {/* key forces re-render when levels, selection or label mode change */}
      <GeoJSON key={`${selectedId}-${showLabels}-${districts.map((d) => d.level).join()}`}
               data={geo} style={style} onEachFeature={onEachFeature} />
    </MapContainer>
  )
}
