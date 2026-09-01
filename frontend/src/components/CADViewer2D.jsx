import React, { useState, useRef, useEffect } from 'react'
import { 
  ZoomIn, ZoomOut, RotateCcw, Eye, Ruler, Download, Printer, Maximize2, Minimize2 
} from 'lucide-react'
import { Button } from './ui/button'

export function CADViewer2D({ svgString, isFullscreen, onToggleFullscreen }) {
  const [transform, setTransform] = useState({ scale: 1, x: 0, y: 0 })
  const [activeLayers, setActiveLayers] = useState({
    walls: true,
    doors: true,
    windows: true,
    dimensions: true,
    annotations: true,
    grid: true
  })


  const [isMeasuring, setIsMeasuring] = useState(false)
  const [measurePoints, setMeasurePoints] = useState([])
  const [measurement, setMeasurement] = useState(null)
  
  const containerRef = useRef(null)
  const svgWrapperRef = useRef(null)
  const isDragging = useRef(false)
  const dragStart = useRef({ x: 0, y: 0 })

  // Reset view on new SVG load
  useEffect(() => {
    setTransform({ scale: 1, x: 0, y: 0 })
    setMeasurePoints([])
    setMeasurement(null)
  }, [svgString])

  // Mouse Wheel Zoom
  const handleWheel = (e) => {
    e.preventDefault()
    const zoomFactor = 1.1
    let newScale = transform.scale
    if (e.deltaY < 0) {
      newScale = Math.min(transform.scale * zoomFactor, 10)
    } else {
      newScale = Math.max(transform.scale / zoomFactor, 0.4)
    }
    
    // Zoom centered on mouse pointer
    if (containerRef.current) {
      const rect = containerRef.current.getBoundingClientRect()
      const mouseX = e.clientX - rect.left
      const mouseY = e.clientY - rect.top
      
      const dx = mouseX - transform.x
      const dy = mouseY - transform.y
      
      const newX = mouseX - dx * (newScale / transform.scale)
      const newY = mouseY - dy * (newScale / transform.scale)
      
      setTransform({ scale: newScale, x: newX, y: newY })
    }
  }

  // Click & Drag Pan
  const handleMouseDown = (e) => {
    if (isMeasuring) {
      handleMeasureClick(e)
      return
    }
    isDragging.current = true
    dragStart.current = { x: e.clientX - transform.x, y: e.clientY - transform.y }
  }

  const handleMouseMove = (e) => {
    if (isDragging.current) {
      setTransform(prev => ({
        ...prev,
        x: e.clientX - dragStart.current.x,
        y: e.clientY - dragStart.current.y
      }))
    }
  }

  const handleMouseUp = () => {
    isDragging.current = false
  }

  // Zoom controls
  const zoomIn = () => setTransform(prev => ({ ...prev, scale: Math.min(prev.scale * 1.2, 10) }))
  const zoomOut = () => setTransform(prev => ({ ...prev, scale: Math.max(prev.scale / 1.2, 0.4) }))
  const resetView = () => setTransform({ scale: 1, x: 0, y: 0 })

  // Measure click
  const handleMeasureClick = (e) => {
    if (!svgWrapperRef.current) return
    const rect = svgWrapperRef.current.getBoundingClientRect()
    
    // Position relative to the transformed SVG coordinate system
    const clickX = (e.clientX - rect.left) / transform.scale
    const clickY = (e.clientY - rect.top) / transform.scale
    
    const newPoints = [...measurePoints, { x: clickX, y: clickY }]
    setMeasurePoints(newPoints)
    
    if (newPoints.length === 2) {
      // Calculate pixel distance
      const dx = newPoints[1].x - newPoints[0].x
      const dy = newPoints[1].y - newPoints[0].y
      const pixelDist = Math.sqrt(dx * dx + dy * dy)
      
      // Conversion factor: 1 ft = 20px (from backend SVG exporter scale)
      const distanceFeet = pixelDist / 20.0
      setMeasurement(distanceFeet)
    } else if (newPoints.length > 2) {
      // Reset to 1st point of new measurement
      setMeasurePoints([{ x: clickX, y: clickY }])
      setMeasurement(null)
    }
  }

  // Download SVG
  const downloadSVG = () => {
    if (!svgString) return
    const blob = new Blob([svgString], { type: 'image/svg+xml;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `blueprint-layout.svg`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
  }

  // Print Drawing
  const printDrawing = () => {
    const printWindow = window.open('', '_blank')
    printWindow.document.write(`
      <html>
        <head>
          <title>Blueprint Print Sheet</title>
          <style>
            body { margin: 0; display: flex; justify-content: center; align-items: center; height: 100vh; }
            svg { width: 100%; height: 100%; max-width: 100%; max-height: 100%; }
          </style>
        </head>
        <body>
          ${svgString}
          <script>
            window.onload = function() { window.print(); window.close(); }
          </script>
        </body>
      </html>
    `)
    printWindow.document.close()
  }

  // Modifies the SVG string dynamically by inserting visibility styles for layers
  const getProcessedSvgHtml = () => {
    if (!svgString) return ''
    
    // Inject display styles based on layer visibility
    let processed = svgString
    Object.entries(activeLayers).forEach(([layer, visible]) => {
      const displayVal = visible ? 'block' : 'none'
      // Replace style for the layers groups
      const pattern = new RegExp(`id="layer_${layer}"`, 'g')
      processed = processed.replace(pattern, `id="layer_${layer}" style="display: ${displayVal};"`)
    })
    
    return processed
  }



  return (
    <div className="flex flex-col w-full h-full bg-[#161722] border border-border relative overflow-hidden select-none">
      
      {/* Top Toolbar */}
      <div className="flex items-center justify-between p-3 border-b border-border bg-[#0d0e15] z-10">
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" className="h-8 px-2" onClick={zoomIn} title="Zoom In">
            <ZoomIn className="w-4 h-4" />
          </Button>
          <Button variant="outline" size="sm" className="h-8 px-2" onClick={zoomOut} title="Zoom Out">
            <ZoomOut className="w-4 h-4" />
          </Button>
          <Button variant="outline" size="sm" className="h-8 px-2" onClick={resetView} title="Reset View">
            <RotateCcw className="w-4 h-4" />
          </Button>
          
          <div className="h-4 w-[1px] bg-border mx-1" />
          
          {/* Measurement Tool */}
          <Button 
            variant={isMeasuring ? "default" : "outline"} 
            size="sm" 
            className={`h-8 px-3 font-mono text-xs ${isMeasuring ? "bg-amber-600 hover:bg-amber-500" : ""}`}
            onClick={() => {
              setIsMeasuring(!isMeasuring)
              setMeasurePoints([])
              setMeasurement(null)
            }}
          >
            <Ruler className="w-4 h-4 mr-2" />
            {isMeasuring ? "MEASURING..." : "MEASURE DISTANCE"}
          </Button>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2">
          {onToggleFullscreen && (
            <Button variant="outline" size="sm" className="h-8 w-8 p-0" onClick={onToggleFullscreen} title={isFullscreen ? "Exit Fullscreen (Esc)" : "Fullscreen Mode"}>
              {isFullscreen ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
            </Button>
          )}
          <Button variant="outline" size="sm" className="h-8 px-3 text-xs font-mono" onClick={downloadSVG}>
            <Download className="w-4 h-4 mr-2" /> SVG
          </Button>
          <Button variant="outline" size="sm" className="h-8 px-3 text-xs font-mono" onClick={printDrawing}>
            <Printer className="w-4 h-4 mr-2" /> PRINT/PDF
          </Button>
        </div>
      </div>

      {/* Main Canvas Area */}
      <div 
        ref={containerRef}
        className={`flex-1 relative overflow-hidden bg-[#0b0f19] ${isMeasuring ? 'cursor-crosshair' : 'cursor-grab active:cursor-grabbing'}`}
        onWheel={handleWheel}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
      >

        <div 
          ref={svgWrapperRef}
          className="absolute transform-gpu origin-top-left w-full h-full flex items-center justify-center pointer-events-none"
          style={{
            transform: `translate(${transform.x}px, ${transform.y}px) scale(${transform.scale})`,
            transition: isDragging.current ? 'none' : 'transform 0.05s ease-out'
          }}
        >
          {svgString ? (
            <div 
              className="w-full h-full max-w-full max-h-full pointer-events-auto"
              dangerouslySetInnerHTML={{ __html: getProcessedSvgHtml() }}
            />
          ) : (
            <div className="text-muted-foreground font-mono text-xs">No active drawing.</div>
          )}

          {/* Interactive Measurement SVG Overlay */}
          {isMeasuring && measurePoints.length > 0 && (
            <svg className="absolute inset-0 w-full h-full pointer-events-none z-20">
              {measurePoints.map((pt, i) => (
                <circle key={i} cx={pt.x * transform.scale} cy={pt.y * transform.scale} r="4" fill="#ef4444" />
              ))}
              {measurePoints.length === 2 && (
                <line 
                  x1={measurePoints[0].x * transform.scale} 
                  y1={measurePoints[0].y * transform.scale} 
                  x2={measurePoints[1].x * transform.scale} 
                  y2={measurePoints[1].y * transform.scale} 
                  stroke="#ef4444" 
                  strokeWidth="2" 
                  strokeDasharray="4,4"
                />
              )}
            </svg>
          )}
        </div>

        {/* Floating Measurements Tooltip */}
        {isMeasuring && measurement !== null && (
          <div className="absolute bottom-4 left-4 bg-background border border-amber-500/50 p-3 rounded-sm font-mono text-xs text-foreground z-10 shadow-lg">
            <span className="text-amber-500 font-bold block uppercase tracking-wide mb-1">CAD MEASUREMENT</span>
            <span>Distance: <b className="text-base text-foreground font-light">{measurement.toFixed(2)} ft</b></span>
          </div>
        )}

        {/* Floating Layers Panel */}
        <div className="absolute top-4 right-4 bg-[#0d0e15]/90 border border-border p-4 rounded-sm z-10 w-44 shadow-lg text-foreground font-mono text-xs space-y-3">
          <div className="flex items-center gap-2 border-b border-border pb-2 text-muted-foreground font-bold uppercase tracking-wider">
            <Eye className="w-4 h-4" /> LAYERS
          </div>
          <div className="space-y-2">
            {Object.keys(activeLayers).map((layer) => (
              <label key={layer} className="flex items-center justify-between cursor-pointer group py-1 hover:text-primary">
                <span className="capitalize">{layer}</span>
                <input 
                  type="checkbox"
                  checked={activeLayers[layer]}
                  onChange={() => setActiveLayers(prev => ({ ...prev, [layer]: !prev[layer] }))}
                  className="rounded border-border text-primary focus:ring-0 bg-[#161722]"
                />
              </label>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
