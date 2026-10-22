<script lang="ts">
  import type { Feature, FeatureCollection, Geometry } from 'geojson'
  import { GeoJSONSource, Map as MapLibre, Marker, setWorkerUrl, type PointLike } from 'maplibre-gl'
  import 'maplibre-gl/dist/maplibre-gl.css'
  // MapLibre loads its worker by a URL computed at runtime, which bundlers cannot follow.
  import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'
  import { onMount } from 'svelte'
  import { colorOf, textOn } from './colors'
  import type { Country, Player } from './types'

  interface Props {
    countries: Record<string, Country>
    players: Player[]
    marked: string[] // selected or fighting countries: outlined, and joined by a line
    onselect?: (code: string) => void // present only while the viewer may choose a country
  }
  let { countries, players, marked, onselect }: Props = $props()

  type World = FeatureCollection<Geometry, { code: string; name: string; lon: number; lat: number }>
  const EMPTY: FeatureCollection = { type: 'FeatureCollection', features: [] }
  // The map's colours come from the stylesheet, so each exists only once.
  const css = (name: string) => getComputedStyle(document.documentElement).getPropertyValue(name).trim()

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
        // A dashed line between two marked countries.
        created.addLayer({
          id: 'line',
          type: 'line',
          source: 'line',
          paint: { 'line-color': css('--ink'), 'line-width': 1.2, 'line-dasharray': [4, 3] },
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
    const [a, b] = marked.map((code) => centres[code])
    const line: Feature | undefined =
      a && b ? { type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: [a, b] } } : undefined
    map.getSource<GeoJSONSource>('line')?.setData(line ?? EMPTY)
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
