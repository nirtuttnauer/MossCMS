import { useEffect, useRef, useState } from 'react'
import type { SceneProps } from './LiquidScene'

export default function ThreeScene({ primary, secondary, background, speed, running }: SceneProps) {
  const container = useRef<HTMLDivElement>(null)
  const [fallback, setFallback] = useState(false)
  const playing = useRef(running)
  const playback = useRef<{ start: () => void; stop: () => void } | null>(null)
  useEffect(() => {
    playing.current = running
    if (running) playback.current?.start(); else playback.current?.stop()
  }, [running])
  useEffect(() => {
    let disposed = false
    let cleanup = () => {}
    setFallback(false)
    void import('three').then(THREE => {
      if (disposed || !container.current) return
      const host = container.current
      let renderer: InstanceType<typeof THREE.WebGLRenderer>
      try { renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, powerPreference: 'low-power' }) }
      catch { setFallback(true); return }
      renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 1.5))
      renderer.setClearColor(background)
      host.appendChild(renderer.domElement)
      const scene = new THREE.Scene()
      const camera = new THREE.PerspectiveCamera(40, 1, 0.1, 100)
      camera.position.set(0, 0, 8.5)
      const geometry = new THREE.TorusKnotGeometry(1.35, 0.36, 180, 24, 2, 3)
      const material = new THREE.MeshStandardMaterial({ color: primary, metalness: 0.7, roughness: 0.24 })
      const knot = new THREE.Mesh(geometry, material)
      knot.position.y = 0.35
      scene.add(knot, new THREE.AmbientLight(secondary, 1.5))
      const key = new THREE.DirectionalLight(primary, 4.5)
      key.position.set(3, 4, 5); scene.add(key)
      const rim = new THREE.PointLight(secondary, 120, 30)
      rim.position.set(-4, -2, 3); scene.add(rim)
      const ringGeometry = new THREE.TorusGeometry(2.7, 0.006, 8, 140)
      const ringMaterial = new THREE.MeshBasicMaterial({ color: secondary, transparent: true, opacity: 0.3 })
      const ring = new THREE.Mesh(ringGeometry, ringMaterial)
      ring.rotation.x = 0.45; ring.rotation.y = 0.3; ring.position.y = 0.35
      scene.add(ring)
      let frame = 0, last = 0, elapsed = 0
      let pointerX = 0, pointerY = 0
      const render = () => renderer.render(scene, camera)
      const resize = () => {
        const { width, height } = host.getBoundingClientRect()
        camera.aspect = Math.max(1, width) / Math.max(1, height); camera.updateProjectionMatrix()
        renderer.setSize(Math.max(1, width), Math.max(1, height)); render()
      }
      const observer = new ResizeObserver(resize)
      observer.observe(host)
      const move = (event: PointerEvent) => {
        const rect = host.getBoundingClientRect()
        pointerX = (event.clientX - rect.left) / rect.width - 0.5
        pointerY = (event.clientY - rect.top) / rect.height - 0.5
      }
      host.addEventListener('pointermove', move)
      const animate = (time: number) => {
        elapsed += (last ? Math.min(40, time - last) : 16) / 1000 * speed; last = time
        knot.rotation.x = elapsed * 0.17 + pointerY * 0.3
        knot.rotation.y = elapsed * 0.24 + pointerX * 0.3
        knot.position.y = 0.35 + Math.sin(elapsed * 0.7) * 0.12
        ring.rotation.z = elapsed * 0.04
        render(); frame = requestAnimationFrame(animate)
      }
      const lost = (event: Event) => { event.preventDefault(); cancelAnimationFrame(frame); setFallback(true) }
      renderer.domElement.addEventListener('webglcontextlost', lost)
      knot.rotation.set(0.4, 0.5, 0)
      resize()
      playback.current = {
        start: () => { if (!frame) { last = 0; frame = requestAnimationFrame(animate) } },
        stop: () => { cancelAnimationFrame(frame); frame = 0; last = 0 },
      }
      if (playing.current) playback.current.start()
      cleanup = () => {
        playback.current?.stop(); playback.current = null; observer.disconnect(); host.removeEventListener('pointermove', move)
        renderer.domElement.removeEventListener('webglcontextlost', lost)
        geometry.dispose(); material.dispose(); ringGeometry.dispose(); ringMaterial.dispose()
        renderer.dispose(); renderer.forceContextLoss(); renderer.domElement.remove()
      }
    }).catch(() => { if (!disposed) setFallback(true) })
    return () => { disposed = true; cleanup() }
  }, [primary, secondary, background, speed])
  return <div ref={container} className="scene-canvas three-scene" aria-hidden="true">{fallback && <div className="three-fallback" style={{ borderColor: primary, boxShadow: `0 0 90px ${secondary}55` }}><span style={{ borderColor: secondary }} /></div>}</div>
}
