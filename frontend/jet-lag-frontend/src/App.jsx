import { useEffect, useMemo, useState } from 'react'
import { decode } from '@msgpack/msgpack'
import { LockKeyhole, Route, Search, X } from 'lucide-react'
import { CircleMarker, MapContainer, Pane, Polyline, TileLayer, Tooltip, ZoomControl } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import './App.css'

const DEFAULT_TIME = () => {
  const now = new Date()
  return `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`
}

// Add future cities here with their graph path and network labels.
const CITIES = [
  { id: 'toronto', name: 'Toronto', region: 'Ontario, Canada', operators: 'TTC + GO', graphPath: '/graph.msgpack', lines: 12 },
]

function CityPicker({ onSelect }) {
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
          {CITIES.map((city) => (
            <button className="city-card" key={city.id} onClick={() => onSelect(city)}>
              <span className="city-card-top"><span className="available-pill"><i />AVAILABLE</span></span>
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
  const [activeCity, setActiveCity] = useState(null)
  const [graphState, setGraphState] = useState({ cityId: null, data: null, error: '' })
  const [selectedStation, setSelectedStation] = useState(null)
  const [startTime, setStartTime] = useState(DEFAULT_TIME)
  const [budget, setBudget] = useState('60')
  const [reachability, setReachability] = useState(null)
  const [search, setSearch] = useState('')

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

  const openStation = (index) => {
    setSelectedStation(index)
    setStartTime(DEFAULT_TIME())
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
  if (!activeCity) return <CityPicker onSelect={setActiveCity} />
  if (loadError) return <main className="app-state error-state"><h1>Couldn’t load the map</h1><p>{loadError}</p></main>
  if (!data || !layers) return <main className="app-state"><span className="loader" /><p>Loading Toronto rail network…</p></main>

  const allSegments = layers.routes.flatMap((route) => route.segments.map((segment) => segment.positions))
  const activeSegments = reachability ? layers.routes.map((route) => ({ ...route, active: routeSegmentsReachable(route.segments) })) : []

  return (
    <main className="app-shell">
      <MapContainer className="network-map" center={[43.72, -79.32]} zoom={9} zoomControl={false} preferCanvas>
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>'
          url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
          className="osm-dark-tiles"
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
        <div className="sidebar-topline"><span><i />{activeCity.name} network</span><button onClick={() => { setActiveCity(null); setReachability(null); setSearch('') }}>All cities</button></div>

        <label className="search-label" htmlFor="station-search">Find a station</label>
        <div className="search-wrap">
          <Search className="search-icon" aria-hidden="true" size={18} />
          <input id="station-search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search the rail network" />
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

        <div className="panel-divider" />
        <div className="section-heading"><h2>Network lines</h2><span>{layers.routes.length} routes</span></div>
        <div className="route-legend">
          {layers.routes.map((route) => <div className="legend-row" key={route.id}><span className="legend-swatch" style={{ backgroundColor: route.color }} /><span>{route.name}</span><small>{route.id.startsWith('go_') ? 'GO' : 'TTC'}</small></div>)}
        </div>
        <div className="panel-footer"><span className="live-dot" />Static GTFS schedules <span>·</span> © OpenStreetMap</div>
      </aside>

      {reachability && <div className="map-caption"><span className="caption-key" />Gray sections are outside your travel window</div>}

      {selectedStation !== null && (
        <div className="modal-scrim" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setSelectedStation(null) }}>
          <section className="query-modal" role="dialog" aria-modal="true" aria-labelledby="modal-title">
            <button className="modal-close" aria-label="Close" onClick={() => setSelectedStation(null)}><X aria-hidden="true" size={17} /></button>
            <p className="eyebrow modal-eyebrow">PLAN YOUR REACH</p>
            <h2 id="modal-title">{stations[selectedStation].name}</h2>
            <p className="modal-subtitle">Choose when you leave and how long you have to move.</p>
            <form onSubmit={submitQuery}>
              <label className="field-label" htmlFor="start-time">Starting time</label>
              <input id="start-time" type="time" value={startTime} onChange={(event) => setStartTime(event.target.value)} required />
              <label className="field-label" htmlFor="travel-time">Travel time</label>
              <div className="number-field"><input id="travel-time" type="number" min="5" max="360" step="5" value={budget} onChange={(event) => setBudget(event.target.value)} required /><span>minutes</span></div>
              <button className="submit-button" type="submit">Show reachable stations</button>
            </form>
            <p className="modal-footnote">Based on scheduled service. Service-day calendars are not applied yet.</p>
          </section>
        </div>
      )}
    </main>
  )
}

export default App
