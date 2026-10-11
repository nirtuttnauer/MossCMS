import { useEffect, useRef } from 'react'

export type SceneProps = { primary: string; secondary: string; background: string; speed: number; running: boolean }
const rgb = (hex: string) => [1, 3, 5].map(offset => parseInt(hex.slice(offset, offset + 2), 16))

// A damped, discrete wave equation: each cell exchanges height with its neighbours.
export default function LiquidScene({ primary, secondary, background, speed, running }: SceneProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const playing = useRef(running)
  const playback = useRef<{ start: () => void; stop: () => void } | null>(null)
  useEffect(() => {
    playing.current = running
    if (running) playback.current?.start(); else playback.current?.stop()
  }, [running])
  useEffect(() => {
    const canvas = canvasRef.current!
    const context = canvas.getContext('2d', { alpha: false })
    if (!context) return
    const width = 190, height = 140
    let previous = new Float32Array(width * height)
    let current = new Float32Array(width * height)
    const buffer = document.createElement('canvas')
    buffer.width = width; buffer.height = height
    const painter = buffer.getContext('2d')!
    const pixels = painter.createImageData(width, height)
    const a = rgb(primary), b = rgb(secondary), base = rgb(background)
    let frame = 0, elapsed = 0, last = 0, lastDrop = -1000, accumulator = 0
    const disturb = (x: number, y: number, strength: number) => {
      for (let dy = -5; dy <= 5; dy++) for (let dx = -5; dx <= 5; dx++) {
        const px = Math.round(x + dx), py = Math.round(y + dy)
        if (px > 1 && py > 1 && px < width - 2 && py < height - 2) {
          const radius = Math.hypot(dx, dy)
          if (radius < 5) current[py * width + px] += Math.cos(radius * Math.PI / 10) * strength
        }
      }
    }
    const paint = () => {
      for (let y = 0; y < height; y++) for (let x = 0; x < width; x++) {
        const index = y * width + x
        const dx = (current[index + 1] ?? 0) - (current[index - 1] ?? 0)
        const dy = (current[index + width] ?? 0) - (current[index - width] ?? 0)
        const refraction = Math.sin(x / 34 + y / 27 + dx * 0.055 + elapsed / 6000) * 0.5 + 0.5
        const light = Math.max(0, Math.min(1, 0.22 + (dx - dy) * 0.035))
        const shine = Math.pow(Math.max(0, 1 - Math.abs(dx * 0.035 - dy * 0.04 - 0.7)), 12) * 0.55
        const vignette = Math.max(0.22, 1 - Math.hypot((x / width - 0.52) * 1.1, (y / height - 0.45) * 1.1))
        for (let channel = 0; channel < 3; channel++) {
          const tint = a[channel] * refraction + b[channel] * (1 - refraction)
          pixels.data[index * 4 + channel] = Math.min(255, (base[channel] * (1 - light) + tint * light + shine * tint) * vignette)
        }
        pixels.data[index * 4 + 3] = 255
      }
      painter.putImageData(pixels, 0, 0)
      context.drawImage(buffer, 0, 0, canvas.width, canvas.height)
    }
    const resize = () => {
      const bounds = canvas.getBoundingClientRect()
      const ratio = Math.min(devicePixelRatio || 1, 1.5)
      canvas.width = Math.max(1, Math.round(bounds.width * ratio)); canvas.height = Math.max(1, Math.round(bounds.height * ratio))
      paint()
    }
    const observer = new ResizeObserver(resize)
    observer.observe(canvas)
    const move = (event: PointerEvent) => {
      if (!playing.current) return
      const bounds = canvas.getBoundingClientRect()
      disturb((event.clientX - bounds.left) / bounds.width * width, (event.clientY - bounds.top) / bounds.height * height, 8)
    }
    canvas.addEventListener('pointermove', move)
    disturb(width * 0.58, height * 0.45, 120)
    disturb(width * 0.25, height * 0.65, 80)
    const animate = (time: number) => {
      const delta = last ? Math.min(40, time - last) : 16
      last = time; elapsed += delta * speed
      if (elapsed - lastDrop > 780) {
        disturb(width * (0.5 + Math.sin(elapsed / 2100) * 0.28), height * (0.5 + Math.cos(elapsed / 1800) * 0.25), 75)
        lastDrop = elapsed
      }
      accumulator += delta * speed
      while (accumulator >= 16) {
        for (let y = 1; y < height - 1; y++) for (let x = 1; x < width - 1; x++) {
          const i = y * width + x
          previous[i] = ((current[i - 1] + current[i + 1] + current[i - width] + current[i + width]) / 2 - previous[i]) * 0.988
        }
        const swap = previous; previous = current; current = swap
        accumulator -= 16
      }
      paint()
      frame = requestAnimationFrame(animate)
    }
    resize()
    playback.current = {
      start: () => { if (!frame) { last = 0; frame = requestAnimationFrame(animate) } },
      stop: () => { cancelAnimationFrame(frame); frame = 0; last = 0 },
    }
    if (playing.current) playback.current.start()
    return () => { playback.current?.stop(); playback.current = null; observer.disconnect(); canvas.removeEventListener('pointermove', move) }
  }, [primary, secondary, background, speed])
  return <canvas className="scene-canvas liquid-canvas" ref={canvasRef} aria-hidden="true" />
}
