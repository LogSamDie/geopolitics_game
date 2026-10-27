<script lang="ts">
  import type { FeatureCollection, Geometry } from 'geojson'
  import { GeoJSONSource, Map as MapLibre, Marker, MercatorCoordinate, setWorkerUrl, type PointLike } from 'maplibre-gl'
  import 'maplibre-gl/dist/maplibre-gl.css'
  // MapLibre computes its worker's URL at runtime, which bundlers cannot follow.
  import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'
  import { onMount } from 'svelte'
  import { colorOf, textOn } from './colors'
  import type { Country, Route } from './types'

  interface Props {
    countries: Record<string, Country>
    marked: string[]
    route?: Route
    onselect?: (code: string) => void
  }
  let { countries, marked, route, onselect }: Props = $props()

  type World = FeatureCollection<Geometry, { code: string; lon: number; lat: number }>
  const empty: FeatureCollection = { type: 'FeatureCollection', features: [] }
  const css = (name: string) => getComputedStyle(document.documentElement).getPropertyValue(name).trim()

  setWorkerUrl(workerUrl)

  let container: HTMLDivElement
  let headElement: HTMLDivElement
  let head: Marker
  let map = $state<MapLibre>() // set once the world is loaded
  const tags: Record<string, HTMLDivElement> = {}
  const centres: Record<string, [number, number]> = {}

  /** A dash pattern shifted along the line, which is how dashes march. */
  function dashes(offset: number, dash: number, gap: number): number[] {
    const shift = offset % (dash + gap)
    return shift < gap ? [0, shift, dash, gap - shift] : [shift - gap, gap, dash - (shift - gap), 0]
  }

  /** A path bowing north, as a function from 0 at the start to 1 at the end. */
  function arc(from: [number, number], to: [number, number]) {
    const [a, b] = [MercatorCoordinate.fromLngLat(from), MercatorCoordinate.fromLngLat(to)]
    const control = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 - 0.18 * Math.hypot(b.x - a.x, b.y - a.y) }
    return (t: number) =>
      new MercatorCoordinate(
        (1 - t) ** 2 * a.x + 2 * t * (1 - t) * control.x + t ** 2 * b.x,
        (1 - t) ** 2 * a.y + 2 * t * (1 - t) * control.y + t ** 2 * b.y,
      )
  }

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
      fitBoundsOptions: { padding: 16 },
      attributionControl: false,
      dragRotate: false,
      pitchWithRotate: false,
      renderWorldCopies: false,
      maxZoom: 6,
    })
    created.touchZoomRotate.disableRotation()
    created.keyboard.disableRotation()

    // The style only loads on an animation frame, which may come after the fetch.
    Promise.all([fetch('/world.geojson').then((r) => r.json() as Promise<World>), created.once('load')]).then(
      ([world]) => {
        created.addSource('world', { type: 'geojson', data: world, promoteId: 'code' })
        created.addSource('line', { type: 'geojson', data: empty })
        created.addLayer({
          id: 'land',
          type: 'fill',
          source: 'world',
          paint: { 'fill-color': ['coalesce', ['feature-state', 'color'], css('--land')] },
        })
        created.addLayer({
          id: 'borders',
          type: 'line',
          source: 'world',
          paint: { 'line-color': css('--border'), 'line-width': 0.6 },
        })
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
        created.addLayer({ id: 'route-edge', type: 'line', source: 'line', paint: { 'line-color': css('--panel') } })
        created.addLayer({ id: 'route', type: 'line', source: 'line', paint: { 'line-color': css('--ink') } })

        const codeAt = (point: PointLike): string | undefined => {
          const code = created.queryRenderedFeatures(point, { layers: ['land'] })[0]?.properties.code
          return code in countries ? code : undefined
        }
        created.on('click', (e) => {
          const code = codeAt(e.point)
          if (code) onselect?.(code)
        })
        created.on('mousemove', (e) => {
          created.getCanvas().style.cursor = onselect && codeAt(e.point) ? 'pointer' : ''
        })

        head = new Marker({ element: headElement, rotationAlignment: 'map', subpixelPositioning: true })
          .setLngLat([0, 0])
          .addTo(created)
        for (const { properties: p } of world.features) {
          centres[p.code] = [p.lon, p.lat]
          if (tags[p.code])
            new Marker({ element: tags[p.code], subpixelPositioning: true }).setLngLat(centres[p.code]).addTo(created)
        }
        map = created
      },
    )

    return () => created.remove()
  })

  $effect(() => {
    if (!map) return
    for (const country of Object.values(countries)) {
      const state = { color: colorOf(country.owner), marked: marked.includes(country.code) }
      map.setFeatureState({ source: 'world', id: country.code }, state)
    }
  })

  $effect(() => {
    const current = map
    if (!current) return
    const line = current.getSource<GeoJSONSource>('line')!
    if (!route) {
      line.setData(empty)
      return
    }
    const path = arc(centres[route.source], centres[route.target])
    line.setData({
      type: 'Feature',
      properties: {},
      geometry: {
        type: 'LineString',
        coordinates: Array.from({ length: 49 }, (_, i) =>
          path(i / 48)
            .toLngLat()
            .toArray(),
        ),
      },
    })
    const moveHead = (t: number) => {
      const [before, after] = [path(t - 0.01), path(t + 0.01)]
      head.setLngLat(path(t).toLngLat())
      head.setRotation((Math.atan2(after.y - before.y, after.x - before.x) * 180) / Math.PI)
    }
    const [dash, gap] = route.attack ? [2.5, 1.8] : [4, 3]
    current.setPaintProperty('route', 'line-width', route.attack ? 2.2 : 1.2)
    current.setPaintProperty('route-edge', 'line-width', route.attack ? 5 : 0)
    current.setPaintProperty('route', 'line-dasharray', dashes(0, dash, gap))
    moveHead(0.5)
    if (!route.live || matchMedia('(prefers-reduced-motion: reduce)').matches) return
    // By the clock, so the motion carries on when a new event redraws the route.
    const march = setInterval(() => {
      const tick = Math.floor(performance.now() / 40)
      current.setPaintProperty('route', 'line-dasharray', dashes(((tick % 24) / 24) * (dash + gap), dash, gap))
      moveHead((tick % 38) / 38)
    }, 40)
    return () => clearInterval(march)
  })
</script>

<div class="map" bind:this={container}></div>

<div
  class="head"
  class:troops={!route?.attack}
  style:display={route?.attack || route?.live ? undefined : 'none'}
  style:--owner={route && colorOf(countries[route.source].owner)}
  bind:this={headElement}
>
  <svg viewBox="0 0 24 24">
    {#if route?.attack}<path d="M21 12 4 4.5 7.5 12 4 19.5Z" />{:else}<circle cx="12" cy="12" r="7.5" />{/if}
  </svg>
</div>

{#each Object.values(countries) as country (country.code)}
  {@const owner = colorOf(country.owner)}
  <div
    class="tag"
    class:marked={marked.includes(country.code)}
    class:clickable={onselect}
    style:--owner={owner}
    style:--on-owner={textOn(owner)}
    bind:this={tags[country.code]}
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

  .head {
    width: 24px;
    height: 24px;
    pointer-events: none;
  }

  .head.troops {
    width: 18px;
    height: 18px;
  }

  .head svg {
    display: block;
    fill: var(--owner);
    stroke: var(--ink);
    stroke-width: 1.5;
    stroke-linejoin: round;
  }

  .tag {
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

  .tag.clickable {
    cursor: pointer;
  }

  .tag.marked {
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

  @keyframes stamp {
    from {
      transform: scale(1.4);
    }
  }

  @media (max-width: 800px), (max-height: 500px) {
    .name {
      display: none;
    }

    .tag {
      padding: 0;
      border: 0;
    }
  }
</style>
