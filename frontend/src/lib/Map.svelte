<script lang="ts">
  import type { FeatureCollection, Geometry } from 'geojson'
  import { GeoJSONSource, Map as MapLibre, Marker, MercatorCoordinate, setWorkerUrl, type PointLike } from 'maplibre-gl'
  import 'maplibre-gl/dist/maplibre-gl.css'
  // MapLibre loads its worker by a URL computed at runtime, which bundlers cannot follow.
  import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'
  import { onMount } from 'svelte'
  import { colorOf, textOn } from './colors'
  import type { Country, Player, Route } from './types'

  interface Props {
    countries: Record<string, Country>
    players: Player[]
    marked: string[] // selected or fighting countries: outlined
    route?: Route
    onselect?: (code: string) => void // present only while the viewer may choose a country
  }
  let { countries, players, marked, route, onselect }: Props = $props()

  type World = FeatureCollection<Geometry, { code: string; name: string; lon: number; lat: number }>
  const EMPTY: FeatureCollection = { type: 'FeatureCollection', features: [] }
  // The map's colours come from the stylesheet, so each exists only once.
  const css = (name: string) => getComputedStyle(document.documentElement).getPropertyValue(name).trim()

  /** A dash pattern shifted along the line by `offset`, which is how dashes march. */
  function dashes(offset: number, dash: number, gap: number): number[] {
    const shift = offset % (dash + gap)
    return shift < gap ? [0, shift, dash, gap - shift] : [shift - gap, gap, dash - (shift - gap), 0]
  }

  /** A curved path bowing north: the point at `t`, from 0 at the start to 1 at the end. */
  function arc(from: [number, number], to: [number, number]) {
    const [a, b] = [MercatorCoordinate.fromLngLat(from), MercatorCoordinate.fromLngLat(to)]
    const control = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 - 0.18 * Math.hypot(b.x - a.x, b.y - a.y) }
    return (t: number) =>
      new MercatorCoordinate(
        (1 - t) ** 2 * a.x + 2 * t * (1 - t) * control.x + t ** 2 * b.x,
        (1 - t) ** 2 * a.y + 2 * t * (1 - t) * control.y + t ** 2 * b.y,
      )
  }

  /** What travels along a route: an arrowhead pointing right, or a circle for marching troops. */
  function arrowhead(fill: string, circle = false): ImageData {
    const context = document.createElement('canvas').getContext('2d')!
    context.canvas.width = context.canvas.height = 48
    if (circle) {
      context.arc(24, 24, 15, 0, 2 * Math.PI)
    } else {
      context.moveTo(42, 24)
      context.lineTo(8, 9)
      context.lineTo(15, 24)
      context.lineTo(8, 39)
      context.closePath()
    }
    context.fillStyle = fill
    context.fill()
    context.strokeStyle = css('--ink')
    context.lineWidth = 3
    context.lineJoin = 'round'
    context.stroke()
    return context.getImageData(0, 0, 48, 48)
  }

  setWorkerUrl(workerUrl)

  let container: HTMLDivElement
  let map = $state<MapLibre>() // set once the world is loaded
  const centres: Record<string, [number, number]> = {}
  let markerElements = $state<Record<string, HTMLDivElement>>({})

  onMount(() => {
    const created = new MapLibre({
      container,
      style: {
        version: 8,
        sources: {},
        layers: [{ id: 'sea', type: 'background', paint: { 'background-color': css('--sea') } }],
      },
      bounds: [
        [-170, -56],
        [180, 78],
      ],
      fitBoundsOptions: { padding: 16 }, // room for tags at the edge of the world
      attributionControl: false,
      dragRotate: false,
      pitchWithRotate: false,
      renderWorldCopies: false,
      maxZoom: 6,
    })
    created.touchZoomRotate.disableRotation()
    created.keyboard.disableRotation()

    // The style finishes loading on an animation frame, which may come after the fetch.
    Promise.all([fetch('/world.geojson').then((r) => r.json() as Promise<World>), created.once('load')]).then(
      ([world]) => {
        created.addSource('world', { type: 'geojson', data: world, promoteId: 'code' })
        created.addSource('line', { type: 'geojson', data: EMPTY })
        created.addSource('arrowhead', { type: 'geojson', data: EMPTY })
        // Countries in the game take their owner's colour from feature state.
        created.addLayer({
          id: 'land',
          type: 'fill',
          source: 'world',
          paint: { 'fill-color': ['coalesce', ['feature-state', 'color'], css('--land')] },
        })
        // Every border and coast.
        created.addLayer({
          id: 'borders',
          type: 'line',
          source: 'world',
          paint: { 'line-color': css('--border'), 'line-width': 0.6 },
        })
        // A double line around marked countries.
        created.addLayer({
          id: 'marked',
          type: 'line',
          source: 'world',
          paint: {
            'line-color': css('--ink'),
            'line-width': ['case', ['boolean', ['feature-state', 'marked'], false], 1.2, 0],
            'line-gap-width': 1.4,
          },
        })
        // The route: a paper edge that only attacks have, the dashes, and the arrowhead.
        created.addLayer({
          id: 'route-edge',
          type: 'line',
          source: 'line',
          paint: { 'line-color': css('--panel') },
        })
        created.addLayer({ id: 'route', type: 'line', source: 'line', paint: { 'line-color': css('--ink') } })
        created.addImage('arrowhead', arrowhead(css('--ink')), { pixelRatio: 2 })
        created.addLayer({
          id: 'route-arrowhead',
          type: 'symbol',
          source: 'arrowhead',
          layout: {
            'icon-image': 'arrowhead',
            'icon-rotate': ['get', 'bearing'],
            'icon-rotation-alignment': 'map',
            'icon-allow-overlap': true,
          },
        })

        const codeAt = (point: PointLike): string | undefined => {
          const code: unknown = created.queryRenderedFeatures(point, { layers: ['land'] })[0]?.properties.code
          return typeof code === 'string' && code in countries ? code : undefined
        }
        created.on('click', (e) => {
          const code = codeAt(e.point)
          if (code !== undefined) onselect?.(code)
        })
        created.on('mousemove', (e) => {
          created.getCanvas().style.cursor = onselect && codeAt(e.point) !== undefined ? 'pointer' : ''
        })
        // One marker per country in the game, so tiny countries stay visible and clickable.
        for (const { properties } of world.features) {
          const centre: [number, number] = [properties.lon, properties.lat]
          centres[properties.code] = centre
          const element = markerElements[properties.code]
          if (element) new Marker({ element, subpixelPositioning: true }).setLngLat(centre).addTo(created)
        }
        map = created
      },
    )

    return () => created.remove()
  })

  $effect(() => {
    if (!map) return
    for (const country of Object.values(countries)) {
      const state = { color: colorOf(players, country.owner), marked: marked.includes(country.code) }
      map.setFeatureState({ source: 'world', id: country.code }, state)
    }
  })

  // Bold dashes and an arrowhead for an attack, fine dashes for a move, and a circle once its troops
  // set off. What is only planned stands still; what is happening marches to the target.
  $effect(() => {
    if (!map) return
    const current = map
    const line = current.getSource<GeoJSONSource>('line')
    const head = current.getSource<GeoJSONSource>('arrowhead')
    const a = route && centres[route.source]
    const b = route && centres[route.target]
    if (!route || !a || !b) {
      line?.setData(EMPTY)
      head?.setData(EMPTY)
      return
    }
    const path = arc(a, b)
    const point = (t: number) => path(t).toLngLat().toArray()
    line?.setData({
      type: 'Feature',
      properties: {},
      geometry: { type: 'LineString', coordinates: Array.from({ length: 49 }, (_, i) => point(i / 48)) },
    })
    const placeHead = (t: number) => {
      const [before, after] = [path(t - 0.01), path(t + 0.01)]
      const bearing = (Math.atan2(after.y - before.y, after.x - before.x) * 180) / Math.PI
      head?.setData({ type: 'Feature', properties: { bearing }, geometry: { type: 'Point', coordinates: point(t) } })
    }
    const [dash, gap] = route.attack ? [2.5, 1.8] : [4, 3]
    current.setPaintProperty('route', 'line-width', route.attack ? 2.2 : 1.2)
    current.setPaintProperty('route-edge', 'line-width', route.attack ? 5 : 0)
    current.setPaintProperty('route', 'line-dasharray', dashes(0, dash, gap))
    current.setLayoutProperty('route-arrowhead', 'icon-size', route.attack ? 1 : 0.75)
    const color = colorOf(players, countries[route.source]?.owner ?? '')
    current.updateImage('arrowhead', arrowhead(color, !route.attack))
    if (route.attack || route.live) placeHead(0.5)
    else head?.setData(EMPTY)
    if (!route.live || matchMedia('(prefers-reduced-motion: reduce)').matches) return
    // Driven by the clock, so the motion carries on when a new event redraws the route.
    const march = setInterval(() => {
      const tick = Math.floor(performance.now() / 40)
      current.setPaintProperty('route', 'line-dasharray', dashes(((tick % 24) / 24) * (dash + gap), dash, gap))
      placeHead((tick % 38) / 38)
    }, 40)
    return () => clearInterval(march)
  })
</script>

<div class="map" bind:this={container}></div>

{#each Object.values(countries) as country (country.code)}
  {@const owner = colorOf(players, country.owner)}
  <div
    class="marker"
    class:marked={marked.includes(country.code)}
    class:clickable={onselect}
    style:--owner={owner}
    style:--on-owner={textOn(owner)}
    bind:this={markerElements[country.code]}
    role="button"
    tabindex="0"
    onclick={(e) => (e.stopPropagation(), onselect?.(country.code))}
    onkeydown={(e) => e.key === 'Enter' && onselect?.(country.code)}
  >
    <span class="name">{country.name}</span>
    {#key country.soldiers}<span class="count">{country.soldiers}</span>{/key}
  </div>
{/each}

<style>
  .map {
    width: 100%;
    height: 100%;
  }

  /* The name in small caps, the count in the owner's colour. */
  .marker {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.1rem 0.15rem 0.1rem 0.45rem;
    background: var(--panel);
    color: var(--ink);
    border: 1px solid var(--border);
    border-radius: 2px;
    font-size: 11px;
    line-height: 1.2;
    white-space: nowrap;
    transition:
      box-shadow 0.15s,
      border-color 0.15s;
  }

  .marker.clickable {
    cursor: pointer;
  }

  .marker.marked {
    border-color: var(--ink);
    box-shadow: 0 0 0 1px var(--ink);
    z-index: 1;
  }

  .name {
    font-variant: small-caps;
    font-weight: 700;
    letter-spacing: 0.06em;
  }

  .count {
    min-width: 1.5rem;
    padding: 0.1rem 0.3rem;
    text-align: center;
    background: var(--owner);
    color: var(--on-owner);
    border: 1px solid var(--border);
    border-radius: 1px;
    font-size: 12px;
    font-weight: 700;
    animation: stamp 0.25s ease-out;
  }

  /* On a phone the names would bury the map; the country list carries them. */
  @media (max-width: 800px), (max-height: 500px) {
    .name {
      display: none;
    }

    .marker {
      padding: 0;
      border: 0;
    }
  }
</style>
