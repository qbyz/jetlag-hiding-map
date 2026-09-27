import { useEffect, useMemo, useState } from 'react'
import { decode } from '@msgpack/msgpack'
import { LockKeyhole, Route, Search, X } from 'lucide-react'
import { CircleMarker, MapContainer, Pane, Polyline, TileLayer, Tooltip, ZoomControl } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import './App.css'

const DEFAULT_TIME = (timeZone = 'UTC') => new Intl.DateTimeFormat('en-GB', {
  timeZone,
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
}).format(new Date())

// Toronto game scores supplied for the current TTC and Toronto GO station inventory.
// Key by normalized display name so graph stop IDs and feed-specific IDs do not matter.
const TORONTO_STATION_SCORES = {
  'finch': { accessibility: 7, uniqueness: 9, zone_quality: 12, search_complexity: 10, endgame_potential: 11, total: 49, status: 'active' },
  'north york centre': { accessibility: 8, uniqueness: 11, zone_quality: 13, search_complexity: 12, endgame_potential: 13, total: 57, status: 'active' },
  'sheppard-yonge': { accessibility: 5, uniqueness: 7, zone_quality: 15, search_complexity: 13, endgame_potential: 14, total: 54, status: 'active' },
  'york mills': { accessibility: 8, uniqueness: 12, zone_quality: 14, search_complexity: 13, endgame_potential: 14, total: 61, status: 'active' },
  'lawrence': { accessibility: 8, uniqueness: 12, zone_quality: 13, search_complexity: 12, endgame_potential: 14, total: 59, status: 'active' },
  'eglinton': { accessibility: 4, uniqueness: 6, zone_quality: 18, search_complexity: 17, endgame_potential: 17, total: 62, status: 'active' },
  'davisville': { accessibility: 8, uniqueness: 12, zone_quality: 15, search_complexity: 14, endgame_potential: 16, total: 65, status: 'active' },
  'st clair': { accessibility: 7, uniqueness: 10, zone_quality: 16, search_complexity: 15, endgame_potential: 16, total: 64, status: 'active' },
  'summerhill': { accessibility: 9, uniqueness: 13, zone_quality: 15, search_complexity: 15, endgame_potential: 16, total: 68, status: 'active' },
  'rosedale': { accessibility: 10, uniqueness: 14, zone_quality: 17, search_complexity: 16, endgame_potential: 17, total: 74, status: 'active' },
  'bloor-yonge': { accessibility: 3, uniqueness: 4, zone_quality: 19, search_complexity: 17, endgame_potential: 18, total: 61, status: 'active' },
  'wellesley': { accessibility: 7, uniqueness: 9, zone_quality: 17, search_complexity: 15, endgame_potential: 17, total: 65, status: 'active' },
  'college': { accessibility: 6, uniqueness: 8, zone_quality: 18, search_complexity: 16, endgame_potential: 18, total: 68, status: 'active' },
  'tmu': { accessibility: 5, uniqueness: 7, zone_quality: 18, search_complexity: 16, endgame_potential: 18, total: 64, status: 'active' },
  'queen': { accessibility: 4, uniqueness: 5, zone_quality: 19, search_complexity: 16, endgame_potential: 18, total: 62, status: 'active' },
  'king': { accessibility: 4, uniqueness: 6, zone_quality: 20, search_complexity: 17, endgame_potential: 18, total: 65, status: 'active' },
  'union': { accessibility: 2, uniqueness: 2, zone_quality: 20, search_complexity: 13, endgame_potential: 16, total: 53, status: 'active' },
  'st andrew': { accessibility: 4, uniqueness: 6, zone_quality: 19, search_complexity: 16, endgame_potential: 18, total: 63, status: 'active' },
  'osgoode': { accessibility: 5, uniqueness: 8, zone_quality: 19, search_complexity: 17, endgame_potential: 18, total: 67, status: 'active' },
  'st patrick': { accessibility: 5, uniqueness: 9, zone_quality: 18, search_complexity: 16, endgame_potential: 17, total: 65, status: 'active' },
  'queen\'s park': { accessibility: 6, uniqueness: 9, zone_quality: 18, search_complexity: 17, endgame_potential: 18, total: 68, status: 'active' },
  'museum': { accessibility: 8, uniqueness: 12, zone_quality: 18, search_complexity: 17, endgame_potential: 18, total: 73, status: 'active' },
  'st george': { accessibility: 4, uniqueness: 6, zone_quality: 19, search_complexity: 17, endgame_potential: 18, total: 64, status: 'active' },
  'spadina': { accessibility: 4, uniqueness: 5, zone_quality: 19, search_complexity: 16, endgame_potential: 18, total: 62, status: 'active' },
  'dupont': { accessibility: 8, uniqueness: 12, zone_quality: 17, search_complexity: 15, endgame_potential: 17, total: 69, status: 'active' },
  'st clair west': { accessibility: 7, uniqueness: 11, zone_quality: 16, search_complexity: 15, endgame_potential: 16, total: 65, status: 'active' },
  'cedarvale': { accessibility: 8, uniqueness: 13, zone_quality: 15, search_complexity: 14, endgame_potential: 15, total: 65, status: 'active' },
  'glencairn': { accessibility: 9, uniqueness: 14, zone_quality: 13, search_complexity: 12, endgame_potential: 14, total: 62, status: 'active' },
  'lawrence west': { accessibility: 9, uniqueness: 13, zone_quality: 14, search_complexity: 13, endgame_potential: 15, total: 64, status: 'active' },
  'yorkdale': { accessibility: 6, uniqueness: 8, zone_quality: 17, search_complexity: 15, endgame_potential: 16, total: 62, status: 'active' },
  'wilson': { accessibility: 9, uniqueness: 14, zone_quality: 14, search_complexity: 13, endgame_potential: 15, total: 65, status: 'active' },
  'sheppard west': { accessibility: 9, uniqueness: 14, zone_quality: 13, search_complexity: 12, endgame_potential: 14, total: 62, status: 'active' },
  'downsview park': { accessibility: 11, uniqueness: 16, zone_quality: 12, search_complexity: 11, endgame_potential: 13, total: 63, status: 'active' },
  'finch west': { accessibility: 8, uniqueness: 11, zone_quality: 13, search_complexity: 12, endgame_potential: 13, total: 57, status: 'active' },
  'york university': { accessibility: 8, uniqueness: 12, zone_quality: 14, search_complexity: 14, endgame_potential: 14, total: 62, status: 'active' },
  'pioneer village': { accessibility: 9, uniqueness: 14, zone_quality: 13, search_complexity: 12, endgame_potential: 14, total: 62, status: 'active' },
  'highway 407': { accessibility: 15, uniqueness: 17, zone_quality: 8, search_complexity: 8, endgame_potential: 9, total: 57, status: 'active' },
  'vaughan metropolitan centre': { accessibility: 11, uniqueness: 15, zone_quality: 12, search_complexity: 11, endgame_potential: 13, total: 62, status: 'active' },
  'kipling': { accessibility: 8, uniqueness: 10, zone_quality: 14, search_complexity: 12, endgame_potential: 14, total: 58, status: 'active' },
  'islington': { accessibility: 9, uniqueness: 12, zone_quality: 14, search_complexity: 13, endgame_potential: 15, total: 63, status: 'active' },
  'royal york': { accessibility: 10, uniqueness: 13, zone_quality: 15, search_complexity: 14, endgame_potential: 16, total: 68, status: 'active' },
  'old mill': { accessibility: 13, uniqueness: 16, zone_quality: 17, search_complexity: 17, endgame_potential: 18, total: 81, status: 'active' },
  'jane': { accessibility: 9, uniqueness: 13, zone_quality: 16, search_complexity: 14, endgame_potential: 16, total: 68, status: 'active' },
  'runnymede': { accessibility: 10, uniqueness: 13, zone_quality: 15, search_complexity: 14, endgame_potential: 16, total: 68, status: 'active' },
  'high park': { accessibility: 11, uniqueness: 14, zone_quality: 18, search_complexity: 17, endgame_potential: 18, total: 78, status: 'active' },
  'keele': { accessibility: 9, uniqueness: 12, zone_quality: 16, search_complexity: 15, endgame_potential: 17, total: 69, status: 'active' },
  'dundas west': { accessibility: 6, uniqueness: 8, zone_quality: 18, search_complexity: 16, endgame_potential: 17, total: 65, status: 'active' },
  'lansdowne': { accessibility: 10, uniqueness: 14, zone_quality: 16, search_complexity: 15, endgame_potential: 17, total: 72, status: 'active' },
  'dufferin': { accessibility: 8, uniqueness: 10, zone_quality: 17, search_complexity: 15, endgame_potential: 17, total: 67, status: 'active' },
  'ossington': { accessibility: 8, uniqueness: 12, zone_quality: 17, search_complexity: 16, endgame_potential: 17, total: 70, status: 'active' },
  'christie': { accessibility: 9, uniqueness: 13, zone_quality: 16, search_complexity: 15, endgame_potential: 17, total: 70, status: 'active' },
  'bathurst': { accessibility: 7, uniqueness: 9, zone_quality: 18, search_complexity: 16, endgame_potential: 18, total: 68, status: 'active' },
  'bay': { accessibility: 5, uniqueness: 8, zone_quality: 19, search_complexity: 18, endgame_potential: 18, total: 68, status: 'active' },
  'sherbourne': { accessibility: 7, uniqueness: 11, zone_quality: 18, search_complexity: 16, endgame_potential: 18, total: 70, status: 'active' },
  'castle frank': { accessibility: 10, uniqueness: 14, zone_quality: 17, search_complexity: 17, endgame_potential: 18, total: 76, status: 'active' },
  'broadview': { accessibility: 6, uniqueness: 9, zone_quality: 18, search_complexity: 17, endgame_potential: 18, total: 68, status: 'active' },
  'chester': { accessibility: 10, uniqueness: 14, zone_quality: 17, search_complexity: 17, endgame_potential: 18, total: 76, status: 'active' },
  'pape': { accessibility: 7, uniqueness: 9, zone_quality: 18, search_complexity: 16, endgame_potential: 18, total: 68, status: 'active' },
  'donlands': { accessibility: 10, uniqueness: 14, zone_quality: 16, search_complexity: 15, endgame_potential: 17, total: 72, status: 'active' },
  'greenwood': { accessibility: 9, uniqueness: 13, zone_quality: 17, search_complexity: 16, endgame_potential: 18, total: 73, status: 'active' },
  'coxwell': { accessibility: 9, uniqueness: 13, zone_quality: 16, search_complexity: 15, endgame_potential: 17, total: 70, status: 'active' },
  'woodbine': { accessibility: 9, uniqueness: 13, zone_quality: 16, search_complexity: 15, endgame_potential: 17, total: 70, status: 'active' },
  'main street': { accessibility: 8, uniqueness: 11, zone_quality: 17, search_complexity: 15, endgame_potential: 17, total: 68, status: 'active' },
  'victoria park': { accessibility: 11, uniqueness: 14, zone_quality: 15, search_complexity: 13, endgame_potential: 16, total: 69, status: 'active' },
  'warden': { accessibility: 12, uniqueness: 15, zone_quality: 13, search_complexity: 12, endgame_potential: 14, total: 66, status: 'active' },
  'kennedy': { accessibility: 5, uniqueness: 6, zone_quality: 16, search_complexity: 14, endgame_potential: 15, total: 56, status: 'active' },
  'scarborough centre': { accessibility: 10, uniqueness: 13, zone_quality: 14, search_complexity: 13, endgame_potential: 15, total: 65, status: 'replacement_bus_only' },
  'union go': { accessibility: 2, uniqueness: 2, zone_quality: 20, search_complexity: 13, endgame_potential: 16, total: 53, status: 'active' },
  'bloor go': { accessibility: 7, uniqueness: 8, zone_quality: 18, search_complexity: 15, endgame_potential: 17, total: 65, status: 'active' },
  'danforth go': { accessibility: 10, uniqueness: 12, zone_quality: 17, search_complexity: 15, endgame_potential: 17, total: 71, status: 'active' },
  'exhibition go': { accessibility: 7, uniqueness: 10, zone_quality: 19, search_complexity: 16, endgame_potential: 18, total: 70, status: 'active' },
  'mimico go': { accessibility: 12, uniqueness: 14, zone_quality: 15, search_complexity: 14, endgame_potential: 16, total: 71, status: 'active' },
  'long branch go': { accessibility: 13, uniqueness: 15, zone_quality: 14, search_complexity: 13, endgame_potential: 15, total: 70, status: 'active' },
  'etobicoke north go': { accessibility: 15, uniqueness: 17, zone_quality: 10, search_complexity: 9, endgame_potential: 12, total: 63, status: 'active' },
  'weston go': { accessibility: 12, uniqueness: 14, zone_quality: 13, search_complexity: 12, endgame_potential: 14, total: 65, status: 'active' },
  'mount dennis go': { accessibility: 12, uniqueness: 16, zone_quality: 14, search_complexity: 14, endgame_potential: 15, total: 71, status: 'active' },
  'kipling go': { accessibility: 9, uniqueness: 11, zone_quality: 15, search_complexity: 13, endgame_potential: 15, total: 63, status: 'active' },
  'downsview park go': { accessibility: 11, uniqueness: 16, zone_quality: 12, search_complexity: 11, endgame_potential: 13, total: 63, status: 'active' },
  'old cummer go': { accessibility: 15, uniqueness: 18, zone_quality: 11, search_complexity: 10, endgame_potential: 13, total: 67, status: 'active' },
  'oriole go': { accessibility: 14, uniqueness: 17, zone_quality: 12, search_complexity: 11, endgame_potential: 14, total: 68, status: 'active' },
  'eglinton go': { accessibility: 15, uniqueness: 18, zone_quality: 10, search_complexity: 9, endgame_potential: 12, total: 64, status: 'active' },
  'kennedy go': { accessibility: 5, uniqueness: 6, zone_quality: 16, search_complexity: 14, endgame_potential: 15, total: 56, status: 'active' },
  'scarborough go': { accessibility: 14, uniqueness: 17, zone_quality: 11, search_complexity: 10, endgame_potential: 13, total: 65, status: 'active' },
  'guildwood go': { accessibility: 16, uniqueness: 18, zone_quality: 10, search_complexity: 10, endgame_potential: 13, total: 67, status: 'active' },
  'rouge hill go': { accessibility: 17, uniqueness: 19, zone_quality: 11, search_complexity: 10, endgame_potential: 13, total: 70, status: 'active' },
  'agincourt go': { accessibility: 15, uniqueness: 18, zone_quality: 11, search_complexity: 10, endgame_potential: 13, total: 67, status: 'active' },
  'milliken go': { accessibility: 15, uniqueness: 18, zone_quality: 10, search_complexity: 9, endgame_potential: 12, total: 64, status: 'active' },
  // Remaining TTC Line 2, 4, 5 and 6 stations.
  'bayview': { accessibility: 10, uniqueness: 13, zone_quality: 15, search_complexity: 15, endgame_potential: 16, total: 69, status: 'active' },
  'bessarion': { accessibility: 12, uniqueness: 16, zone_quality: 12, search_complexity: 11, endgame_potential: 14, total: 65, status: 'active' },
  'leslie': { accessibility: 12, uniqueness: 15, zone_quality: 13, search_complexity: 12, endgame_potential: 14, total: 66, status: 'active' },
  'don mills': { accessibility: 10, uniqueness: 12, zone_quality: 16, search_complexity: 15, endgame_potential: 16, total: 69, status: 'active' },
  'mount dennis': { accessibility: 12, uniqueness: 16, zone_quality: 14, search_complexity: 14, endgame_potential: 15, total: 71, status: 'active' },
  'keelesdale': { accessibility: 11, uniqueness: 15, zone_quality: 14, search_complexity: 14, endgame_potential: 15, total: 69, status: 'active' },
  'caledonia': { accessibility: 12, uniqueness: 16, zone_quality: 13, search_complexity: 13, endgame_potential: 14, total: 68, status: 'active' },
  'fairbank': { accessibility: 11, uniqueness: 14, zone_quality: 16, search_complexity: 15, endgame_potential: 16, total: 72, status: 'active' },
  'oakwood': { accessibility: 10, uniqueness: 13, zone_quality: 17, search_complexity: 16, endgame_potential: 17, total: 73, status: 'active' },
  'forest hill': { accessibility: 11, uniqueness: 15, zone_quality: 16, search_complexity: 16, endgame_potential: 17, total: 75, status: 'active' },
  'chaplin': { accessibility: 11, uniqueness: 14, zone_quality: 15, search_complexity: 14, endgame_potential: 16, total: 70, status: 'active' },
  'avenue': { accessibility: 10, uniqueness: 13, zone_quality: 16, search_complexity: 15, endgame_potential: 17, total: 71, status: 'active' },
  'mount pleasant': { accessibility: 10, uniqueness: 14, zone_quality: 16, search_complexity: 15, endgame_potential: 17, total: 72, status: 'active' },
  'leaside': { accessibility: 11, uniqueness: 14, zone_quality: 15, search_complexity: 15, endgame_potential: 16, total: 71, status: 'active' },
  'laird': { accessibility: 10, uniqueness: 14, zone_quality: 14, search_complexity: 13, endgame_potential: 15, total: 66, status: 'active' },
  'sunnybrook park': { accessibility: 13, uniqueness: 17, zone_quality: 16, search_complexity: 17, endgame_potential: 18, total: 81, status: 'active' },
  'don valley': { accessibility: 14, uniqueness: 18, zone_quality: 15, search_complexity: 16, endgame_potential: 18, total: 81, status: 'active' },
  'aga khan park & museum': { accessibility: 12, uniqueness: 16, zone_quality: 17, search_complexity: 17, endgame_potential: 18, total: 80, status: 'active' },
  'wynford': { accessibility: 13, uniqueness: 16, zone_quality: 13, search_complexity: 12, endgame_potential: 15, total: 69, status: 'active' },
  'sloane': { accessibility: 13, uniqueness: 17, zone_quality: 12, search_complexity: 11, endgame_potential: 14, total: 67, status: 'active' },
  'o\'connor': { accessibility: 13, uniqueness: 16, zone_quality: 14, search_complexity: 13, endgame_potential: 15, total: 71, status: 'active' },
  'pharmacy': { accessibility: 13, uniqueness: 16, zone_quality: 15, search_complexity: 14, endgame_potential: 16, total: 74, status: 'active' },
  'hakimi lebovic': { accessibility: 13, uniqueness: 17, zone_quality: 12, search_complexity: 11, endgame_potential: 14, total: 67, status: 'active' },
  'golden mile': { accessibility: 13, uniqueness: 17, zone_quality: 13, search_complexity: 12, endgame_potential: 15, total: 70, status: 'active' },
  'birchmount': { accessibility: 13, uniqueness: 16, zone_quality: 14, search_complexity: 13, endgame_potential: 15, total: 71, status: 'active' },
  'ionview': { accessibility: 12, uniqueness: 16, zone_quality: 14, search_complexity: 14, endgame_potential: 15, total: 71, status: 'active' },
  'sentinel': { accessibility: 12, uniqueness: 16, zone_quality: 12, search_complexity: 11, endgame_potential: 13, total: 64, status: 'active' },
  'tobermory': { accessibility: 13, uniqueness: 17, zone_quality: 11, search_complexity: 10, endgame_potential: 13, total: 64, status: 'active' },
  'driftwood': { accessibility: 13, uniqueness: 16, zone_quality: 12, search_complexity: 11, endgame_potential: 14, total: 66, status: 'active' },
  'jane and finch': { accessibility: 10, uniqueness: 13, zone_quality: 15, search_complexity: 14, endgame_potential: 16, total: 68, status: 'active' },
  'norfinch oakdale': { accessibility: 14, uniqueness: 18, zone_quality: 11, search_complexity: 10, endgame_potential: 13, total: 66, status: 'active' },
  'signet arrow': { accessibility: 14, uniqueness: 18, zone_quality: 10, search_complexity: 9, endgame_potential: 12, total: 63, status: 'active' },
  'emery': { accessibility: 13, uniqueness: 17, zone_quality: 12, search_complexity: 11, endgame_potential: 14, total: 67, status: 'active' },
  'milvan rumike': { accessibility: 14, uniqueness: 18, zone_quality: 11, search_complexity: 10, endgame_potential: 13, total: 66, status: 'active' },
  'duncanwoods': { accessibility: 14, uniqueness: 18, zone_quality: 10, search_complexity: 9, endgame_potential: 12, total: 63, status: 'active' },
  'pearldale': { accessibility: 14, uniqueness: 18, zone_quality: 10, search_complexity: 9, endgame_potential: 12, total: 63, status: 'active' },
  'rowntree mills': { accessibility: 14, uniqueness: 17, zone_quality: 11, search_complexity: 10, endgame_potential: 13, total: 65, status: 'active' },
  'mount olive': { accessibility: 14, uniqueness: 17, zone_quality: 12, search_complexity: 11, endgame_potential: 13, total: 67, status: 'active' },
  'stevenson': { accessibility: 15, uniqueness: 18, zone_quality: 10, search_complexity: 9, endgame_potential: 12, total: 64, status: 'active' },
  'albion': { accessibility: 13, uniqueness: 16, zone_quality: 12, search_complexity: 11, endgame_potential: 14, total: 66, status: 'active' },
  'martin grove': { accessibility: 13, uniqueness: 16, zone_quality: 13, search_complexity: 12, endgame_potential: 15, total: 69, status: 'active' },
  'westmore': { accessibility: 14, uniqueness: 17, zone_quality: 11, search_complexity: 10, endgame_potential: 13, total: 65, status: 'active' },
  'humber college': { accessibility: 12, uniqueness: 15, zone_quality: 16, search_complexity: 15, endgame_potential: 16, total: 74, status: 'active' },
}

const SCORE_CRITERIA = [
  ['accessibility', 'Accessibility'],
  ['uniqueness', 'Uniqueness'],
  ['zone_quality', 'Zone quality'],
  ['search_complexity', 'Search complexity'],
  ['endgame_potential', 'Endgame potential'],
]

function stationScore(station) {
  if (!station) return null
  const agencies = station.agencies.map((agency) => agency.toLocaleLowerCase())
  if (!agencies.includes('ttc') && !agencies.includes('go')) return null
  let key = station.name.toLocaleLowerCase()
    .replace(/\s*[-–]\s*(?:(?:north|south|east|west)bound\s+)?platform\b.*$/i, '')
    .replace(/\s+(?:(?:north|south|east|west)bound\s+)?platform\b.*$/i, '')
    .replace(/\s+station\b/i, '')
    .replace(/\s+/g, ' ')
    .trim()
  key = key.replace(/\s+go$/i, '').trim()
  if (agencies.includes('go')) key += ' go'
  return TORONTO_STATION_SCORES[key] ?? null
}

function CityPicker({ cities, onSelect }) {
  return (
    <main className="city-picker">
      <div className="city-picker-glow city-picker-glow-one" />
      <div className="city-picker-glow city-picker-glow-two" />
      <header className="city-picker-header">
        <span>TRANSIT ISOCHRONE GENERATOR</span>
      </header>
      <section className="city-picker-content">
        <h1>Cities</h1>
        <div className="city-grid" aria-label="Available cities">
          {cities.map((city) => (
            <button className="city-card" key={city.id} onClick={() => onSelect(city)}>
              <span className="city-card-name">{city.name}</span>
              <span className="city-card-region">{city.region}</span>
              <span className="city-card-bottom"><span>{city.operators}</span><span>{city.lines} lines</span></span>
              <span className="city-card-action">Explore network</span>
            </button>
          ))}
        </div>
        <p className="city-picker-note">More cities will appear here as networks are added.</p>
      </section>
    </main>
  )
}

function buildLayers(data) {
  const routeByIndex = data.routes
  const segmentsByRoute = routeByIndex.map(() => new Map())
  const routesByStop = data.stops.map(() => new Set())

  data.graph.forEach((node, from) => {
    for (const edge of node.transit) {
      const fromStop = data.stops[from]
      const toStop = data.stops[edge.to]
      if (!fromStop || !toStop) continue
      const segment = [
        [fromStop.lat, fromStop.lon],
        [toStop.lat, toStop.lon],
      ]
      for (const trip of edge.trips) {
        const routeIndex = trip[2]
        if (!routeByIndex[routeIndex]) continue
        const key = from < edge.to ? `${from}:${edge.to}` : `${edge.to}:${from}`
        segmentsByRoute[routeIndex].set(key, { positions: segment, from, to: edge.to })
        routesByStop[from].add(routeIndex)
        routesByStop[edge.to].add(routeIndex)
      }
    }
  })

  return {
    routes: routeByIndex.map((route, index) => ({
      ...route,
      segments: route.segments?.length
        ? route.segments
        : [...segmentsByRoute[index].values()],
    })),
    routesByStop,
  }
}

function buildStations(data) {
  const groups = new Map()
  const normalizeName = (name) => name
    .replace(/\s*[-–]\s*(?:(?:north|south|east|west)bound\s+)?platform\b.*$/i, '')
    .replace(/\s+GO$/i, '')
    .trim()

  data.stops.forEach((stop, index) => {
    const name = normalizeName(stop.name)
    const agencyPrefix = stop.id.split('_', 1)[0]
    const key = stop.parent !== null && stop.parent !== undefined
      ? `parent:${agencyPrefix}:${stop.parent}`
      : `name:${name.toLocaleLowerCase()}`
    if (!groups.has(key)) {
      groups.set(key, { name, lat: 0, lon: 0, stopIndices: [], modes: new Set(), agencies: new Set() })
    }
    const group = groups.get(key)
    group.lat += stop.lat
    group.lon += stop.lon
    group.stopIndices.push(index)
    stop.modes.forEach((mode) => group.modes.add(mode))
    group.agencies.add(stop.agency)
  })

  return [...groups.values()].map((group) => ({
    ...group,
    lat: group.lat / group.stopIndices.length,
    lon: group.lon / group.stopIndices.length,
    modes: [...group.modes],
    agencies: [...group.agencies],
  })).sort((a, b) => a.name.localeCompare(b.name))
}

function reachableFrom(data, startingStops, startTime, budgetMinutes) {
  const [hours, minutes] = startTime.split(':').map(Number)
  const initialTime = hours * 3600 + minutes * 60
  const deadline = initialTime + Number(budgetMinutes) * 60
  const arrivals = new Float64Array(data.stops.length)
  arrivals.fill(Number.POSITIVE_INFINITY)
  const visited = new Uint8Array(data.stops.length)
  const departuresFor = new WeakMap()
  const queue = startingStops.map((index) => {
    arrivals[index] = initialTime
    return [initialTime, index]
  })

  while (queue.length) {
    queue.sort((a, b) => b[0] - a[0])
    const [time, stopIndex] = queue.pop()
    if (time > arrivals[stopIndex] || visited[stopIndex]) continue
    if (time > deadline) break
    visited[stopIndex] = 1

    for (const edge of data.graph[stopIndex].transfer) {
      const nextTime = time + edge.duration
      if (nextTime <= deadline && nextTime < arrivals[edge.to]) {
        arrivals[edge.to] = nextTime
        queue.push([nextTime, edge.to])
      }
    }

    for (const edge of data.graph[stopIndex].transit) {
      let departures = departuresFor.get(edge)
      if (!departures) {
        departures = edge.trips.map((trip) => trip[0])
        departuresFor.set(edge, departures)
      }
      let low = 0
      let high = departures.length
      while (low < high) {
        const mid = (low + high) >>> 1
        if (departures[mid] < time) low = mid + 1
        else high = mid
      }
      if (low === edge.trips.length) continue
      const arrival = edge.trips[low][1]
      if (arrival <= deadline && arrival < arrivals[edge.to]) {
        arrivals[edge.to] = arrival
        queue.push([arrival, edge.to])
      }
    }
  }

  return arrivals
}

function PasswordLock({ onUnlock }) {
  const [password, setPassword] = useState('')
  const [error, setError] = useState(false)

  const submitPassword = (event) => {
    event.preventDefault()
    if (password === 'howdy') {
      onUnlock()
      return
    }
    setPassword('')
    setError(true)
  }

  return (
    <main className="password-lock">
      <form className="password-card" onSubmit={submitPassword}>
        <div className="password-icon"><LockKeyhole aria-hidden="true" size={21} /></div>
        <p className="eyebrow">TRANSIT ISOCHRONE GENERATOR</p>
        <h1>Enter password</h1>
        <label className="password-label" htmlFor="site-password">Password</label>
        <input
          autoFocus
          autoComplete="current-password"
          id="site-password"
          onChange={(event) => { setPassword(event.target.value); setError(false) }}
          type="password"
          value={password}
        />
        {error && <p className="password-error" role="alert">That password didn’t work. Try again.</p>}
        <button className="submit-button" type="submit">Unlock</button>
      </form>
    </main>
  )
}

function App() {
  const [unlocked, setUnlocked] = useState(false)
  const [cities, setCities] = useState(null)
  const [cityLoadError, setCityLoadError] = useState('')
  const [activeCity, setActiveCity] = useState(null)
  const [graphState, setGraphState] = useState({ cityId: null, data: null, error: '' })
  const [selectedStation, setSelectedStation] = useState(null)
  const [startTime, setStartTime] = useState(DEFAULT_TIME)
  const [budget, setBudget] = useState('60')
  const [reachability, setReachability] = useState(null)
  const [search, setSearch] = useState('')
  const [stationSort, setStationSort] = useState('score')

  useEffect(() => {
    let active = true
    fetch('/cities.json')
      .then((response) => {
        if (!response.ok) throw new Error('The city list could not be loaded. Run the data pipeline to generate it.')
        return response.json()
      })
      .then((manifest) => {
        if (active) setCities(manifest)
      })
      .catch((error) => {
        if (active) setCityLoadError(error.message || 'The city list could not be loaded.')
      })
    return () => { active = false }
  }, [])

  useEffect(() => {
    if (!activeCity) return undefined
    let active = true
    fetch(activeCity.graphPath)
      .then((response) => {
        if (!response.ok) throw new Error('The station graph could not be loaded.')
        return response.arrayBuffer()
      })
      .then((buffer) => decode(new Uint8Array(buffer)))
      .then((graph) => {
        if (active) setGraphState({ cityId: activeCity.id, data: graph, error: '' })
      })
      .catch((error) => {
        if (active) setGraphState({ cityId: activeCity.id, data: null, error: error.message || 'The station graph could not be loaded.' })
      })
    return () => { active = false }
  }, [activeCity])

  const data = graphState.cityId === activeCity?.id ? graphState.data : null
  const loadError = graphState.cityId === activeCity?.id ? graphState.error : ''
  const layers = useMemo(() => (data ? buildLayers(data) : null), [data])
  const stations = useMemo(() => (data ? buildStations(data) : []), [data])
  const matchingStops = useMemo(() => {
    if (!data || !search.trim()) return []
    const query = search.trim().toLowerCase()
    return stations
      .map((station, index) => ({ station, index }))
      .filter(({ station }) => station.name.toLowerCase().includes(query))
      .slice(0, 6)
  }, [data, search, stations])
  const stationRows = useMemo(() => {
    if (!layers) return []
    const rows = stations.map((station, index) => {
      const routeIndices = [...new Set(station.stopIndices.flatMap((stopIndex) => [...layers.routesByStop[stopIndex]]))]
      const lines = routeIndices.map((routeIndex) => layers.routes[routeIndex]?.name).filter(Boolean)
      return { station, index, lines, lineLabel: lines.join(', '), score: activeCity?.id === 'toronto' ? stationScore(station) : null }
    })
    const sortKey = stationSort === 'score' && activeCity?.id !== 'toronto' ? 'name' : stationSort
    rows.sort((a, b) => {
      if (sortKey === 'line') return a.lineLabel.localeCompare(b.lineLabel) || a.station.name.localeCompare(b.station.name)
      if (sortKey === 'name') return a.station.name.localeCompare(b.station.name)
      const key = sortKey === 'score' ? 'total' : sortKey
      const aValue = a.score?.[key]
      const bValue = b.score?.[key]
      if (aValue == null && bValue == null) return a.station.name.localeCompare(b.station.name)
      if (aValue == null) return 1
      if (bValue == null) return -1
      return bValue - aValue || a.station.name.localeCompare(b.station.name)
    })
    return rows
  }, [activeCity, layers, stationSort, stations])

  const openStation = (index) => {
    setSelectedStation(index)
    setStartTime(DEFAULT_TIME(activeCity?.timeZone))
  }

  const submitQuery = (event) => {
    event.preventDefault()
    if (!data || selectedStation === null) return
    setReachability({
      station: selectedStation,
      arrivals: reachableFrom(data, stations[selectedStation].stopIndices, startTime, budget),
      budget: Number(budget),
      startTime,
    })
    setSelectedStation(null)
    setSearch('')
  }

  const clearQuery = () => setReachability(null)
  const reachableCount = reachability
    ? stations.filter((station) => station.stopIndices.some((index) => Number.isFinite(reachability.arrivals[index]))).length
    : 0
  const routeSegmentsReachable = (segments) => segments
    .filter((segment) => Number.isFinite(reachability.arrivals[segment.from]) && Number.isFinite(reachability.arrivals[segment.to]))
    .map((segment) => segment.positions)

  if (!unlocked) return <PasswordLock onUnlock={() => setUnlocked(true)} />
  if (cityLoadError) return <main className="app-state error-state"><h1>Couldn’t load cities</h1><p>{cityLoadError}</p></main>
  if (!cities) return <main className="app-state"><span className="loader" /><p>Loading cities…</p></main>
  if (!activeCity) return <CityPicker cities={cities} onSelect={setActiveCity} />
  if (loadError) return <main className="app-state error-state"><h1>Couldn’t load the map</h1><p>{loadError}</p></main>
  if (!data || !layers) return <main className="app-state"><span className="loader" /><p>Loading {activeCity.name} network…</p></main>

  const allSegments = layers.routes.flatMap((route) => route.segments.map((segment) => segment.positions))
  const activeSegments = reachability ? layers.routes.map((route) => ({ ...route, active: routeSegmentsReachable(route.segments) })) : []

  return (
    <main className="app-shell">
      <MapContainer className="network-map" center={data.center || [43.72, -79.32]} zoom={data.initialZoom || 9} zoomControl={false} preferCanvas>
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>'
          url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
          className={activeCity.id === 'salt-spring-island' ? 'osm-salt-spring-tiles' : 'osm-dark-tiles'}
          maxZoom={20}
        />
        <ZoomControl position="bottomright" />

        <Pane name="route-lines" style={{ zIndex: 410 }}>
          {layers.routes.map((route) => (
            <Polyline key={`route-${route.id}`} positions={route.segments.map((segment) => segment.positions)} pathOptions={{ color: route.color, weight: 4, opacity: 0.78, lineCap: 'round' }} />
          ))}
          {reachability && <Polyline positions={allSegments} pathOptions={{ color: '#777f85', weight: 7, opacity: 0.76, lineCap: 'round' }} />}
          {reachability && activeSegments.map((route) => (
            <Polyline key={`reachable-${route.id}`} positions={route.active} pathOptions={{ color: route.color, weight: 4.5, opacity: 1, lineCap: 'round' }} />
          ))}
        </Pane>

        <Pane name="station-markers" style={{ zIndex: 640 }}>
          {stations.map((station, index) => {
          const reachable = !reachability || station.stopIndices.some((stopIndex) => Number.isFinite(reachability.arrivals[stopIndex]))
          const isStart = reachability?.station === index
          const routeIndex = station.stopIndices.map((stopIndex) => layers.routesByStop[stopIndex].values().next().value).find((value) => value !== undefined)
          const color = routeIndex === undefined ? '#c4d0d4' : data.routes[routeIndex].color
          return (
            <CircleMarker
              key={`${station.name}-${index}`}
              center={[station.lat, station.lon]}
              radius={isStart ? 8 : 5}
              pathOptions={{
                color: reachable ? '#eef4f5' : '#626c72',
                weight: isStart ? 3 : 1.5,
                fillColor: reachable ? color : '#626c72',
                fillOpacity: reachable ? 1 : 0.82,
              }}
              eventHandlers={{ click: () => openStation(index) }}
            >
              <Tooltip direction="top" offset={[0, -6]}>{station.name}</Tooltip>
            </CircleMarker>
          )
          })}
        </Pane>
      </MapContainer>

      <aside className="network-panel">
        <div className="sidebar-topline"><span><i />{activeCity.name}</span><button onClick={() => { setActiveCity(null); setReachability(null); setSearch('') }}>All cities</button></div>

        <label className="search-label" htmlFor="station-search">Find a station</label>
        <div className="search-wrap">
          <Search className="search-icon" aria-hidden="true" size={18} />
          <input id="station-search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search the network" />
        </div>
        {matchingStops.length > 0 && <div className="search-results">{matchingStops.map(({ station, index }) => <button key={`${station.name}-${index}`} onClick={() => { openStation(index); setSearch('') }}><span>{station.name}</span><small>{station.agencies.map((agency) => agency.toUpperCase()).join(' · ')}</small></button>)}</div>}

        {reachability ? (
          <section className="result-card">
            <div className="result-icon"><Route aria-hidden="true" size={17} /></div>
            <div><p className="result-kicker">REACHABLE NETWORK</p><strong>{reachableCount} stations</strong><p>from {stations[reachability.station].name} · {reachability.budget} min</p></div>
            <button className="text-button" onClick={clearQuery}>Clear</button>
          </section>
        ) : (
          <div className="hint-card"><span className="hint-dot" /><span>Select any station marker on the map to begin.</span></div>
        )}

        <section className="station-directory" aria-label="Station directory">
          <div className="directory-heading">
            <div className="section-heading"><h2>Stations</h2><span>{stations.length}</span></div>
            <label className="sort-control"><span>Sort</span><select value={stationSort} onChange={(event) => setStationSort(event.target.value)} aria-label="Sort stations">
              {activeCity.id === 'toronto' && <>
                <option value="score">Hiding score</option>
                {SCORE_CRITERIA.map(([key, label]) => <option key={key} value={key}>{label}</option>)}
              </>}
              <option value="line">Line</option>
              <option value="name">Name</option>
            </select></label>
          </div>
          <div className="station-list">
            {stationRows.map(({ station, index, lineLabel, score }) => <button className="station-list-row" key={`${station.name}-${index}`} onClick={() => openStation(index)}>
              <span className="station-list-copy"><span>{station.name}</span><small>{lineLabel || station.agencies.map((agency) => agency.toUpperCase()).join(' · ')}</small></span>
              {score && <span className="station-list-score" aria-label={`Hiding score ${score.total} out of 100`}>{score.total}</span>}
            </button>)}
          </div>
        </section>

        <div className="panel-divider" />
        <div className="section-heading"><h2>Network lines</h2><span>{layers.routes.length} routes</span></div>
        <div className="route-legend">
          {layers.routes.map((route) => <div className="legend-row" key={route.id}><span className="legend-swatch" style={{ backgroundColor: route.color }} /><span>{route.name}</span><small>{activeCity.id === 'toronto' ? (route.id.startsWith('go_') ? 'GO' : 'TTC') : activeCity.operators}</small></div>)}
        </div>
        <div className="panel-footer"><span className="live-dot" />Static GTFS schedules <span>·</span> © OpenStreetMap</div>
      </aside>

      {reachability && <div className="map-caption"><span className="caption-key" />Gray sections are outside your travel window</div>}

      {selectedStation !== null && (
        <div className="modal-scrim" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setSelectedStation(null) }}>
          <section className="query-modal" role="dialog" aria-modal="true" aria-labelledby="modal-title">
            <button className="modal-close" aria-label="Close" onClick={() => setSelectedStation(null)}><X aria-hidden="true" size={17} /></button>
            {(() => {
              const score = activeCity.id === 'toronto' ? stationScore(stations[selectedStation]) : null
              return <>
            <p className="eyebrow modal-eyebrow">{score ? 'STATION SCORE' : 'PLAN YOUR REACH'}</p>
            <h2 id="modal-title">{stations[selectedStation].name}</h2>
            {score && <div className="station-score-block">
              <div className="score-total"><div><span>GAME SCORE</span><small>out of 100</small></div><strong>{score.total}<span>/100</span></strong></div>
              <div className="score-criteria">{SCORE_CRITERIA.map(([key, label]) => <div className="score-criterion" key={key}><div><span>{label}</span><strong>{score[key]}<small>/20</small></strong></div><div className="score-track"><span style={{ width: `${score[key] * 5}%` }} /></div></div>)}</div>
              {score.status === 'replacement_bus_only' && <p className="score-status">Line 3 replacement bus station</p>}
              <p className="score-explainer">Each category is scored from 0 to 20. Higher totals indicate a stronger station for the game.</p>
            </div>}
            <p className="modal-subtitle">Choose when you leave and how long you have to move.</p>
            <form onSubmit={submitQuery}>
              <label className="field-label" htmlFor="start-time">Starting time</label>
              <input id="start-time" type="time" value={startTime} onChange={(event) => setStartTime(event.target.value)} required />
              <label className="field-label" htmlFor="travel-time">Travel time</label>
              <div className="number-field"><input id="travel-time" type="number" min="5" max="360" step="5" value={budget} onChange={(event) => setBudget(event.target.value)} required /><span>minutes</span></div>
              <button className="submit-button" type="submit">Show reachable stations</button>
            </form>
            <p className="modal-footnote">Based on scheduled service. Service-day calendars are not applied yet.{activeCity.id === 'toronto' && !score ? ' No game score is available for this stop.' : ''}</p>
              </>
            })()}
          </section>
        </div>
      )}
    </main>
  )
}

export default App
