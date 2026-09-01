import { useState, useRef, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Maximize2, Minimize2 } from 'lucide-react'
import axios from 'axios'
import { BuildingInputForm } from '@/components/BuildingInputForm'
import { BuildingViewer3D } from '@/components/BuildingViewer3D'
import { CompilationStatus } from '@/components/CompilationStatus'
import { ResultsPanel } from '@/components/ResultsPanel'
import { CADViewer2D } from '@/components/CADViewer2D'


export default function Home() {
  const [buildingData, setBuildingData] = useState(null)
  const [isLoading, setIsLoading] = useState(false)
  const [compilationStages, setCompilationStages] = useState([])
  const [currentStage, setCurrentStage] = useState(undefined)
  const [results, setResults] = useState(null)
  const [showResults, setShowResults] = useState(false)
  const [explanation, setExplanation] = useState(null)
  const [viewMode, setViewMode] = useState('3d')
  const [isFullscreen, setIsFullscreen] = useState(false)
  const viewerContainerRef = useRef(null)




  const toggleFullscreen = () => {
    if (!document.fullscreenElement) {
      if (viewerContainerRef.current?.requestFullscreen) {
        viewerContainerRef.current.requestFullscreen().catch((err) => {
          console.error("Error enabling fullscreen:", err)
        })
      }
      setIsFullscreen(true)
    } else {
      if (document.exitFullscreen) {
        document.exitFullscreen()
      }
      setIsFullscreen(false)
    }
  }

  useEffect(() => {
    const handleFullscreenChange = () => {
      setIsFullscreen(!!document.fullscreenElement)
    }
    document.addEventListener('fullscreenchange', handleFullscreenChange)
    return () => document.removeEventListener('fullscreenchange', handleFullscreenChange)
  }, [])

  const handleCompilation = async (params) => {
    setIsLoading(true)
    setShowResults(false)
    setCurrentStage(0)
    setBuildingData(null)
    setResults(null)
    setExplanation(null)
    setViewMode('3d')


    const stages = [
      {
        name: 'Intent Parsing',
        description: 'Tokenizing design brief into constraint parameters',
        status: 'running',
      },
      {
        name: 'Topological Validation',
        description: 'Constructing DAG for privacy flow validation',
        status: 'pending',
      },
      {
        name: 'Geometric Constraints',
        description: 'Subtracting municipal setbacks from plot polygon',
        status: 'pending',
      },
      {
        name: 'MILP Optimization',
        description: 'Packing rooms using integer programming solver',
        status: 'pending',
      },
      {
        name: 'Ventilation Routing',
        description: 'Computing airflow topology through rooms',
        status: 'pending',
      },
      {
        name: '3D Rendering',
        description: 'Extruding blueprint into WebGL geometry',
        status: 'pending',
      },
    ]

    setCompilationStages(stages)

    try {
      const promptText = `A G+${params.floors - 1} house on a ${params.plotWidth}x${params.plotDepth} ft plot with a front road setback of ${params.setbacks.front || 5.0} ft. Design brief: ${params.description}`
      const payload = {
        prompt: promptText
      }

      // Step 1: Let the parser visual execute briefly
      await new Promise((resolve) => setTimeout(resolve, 600))

      // Trigger the real compilation API call to the AI Parsing Layer
      const response = await axios.post(`${import.meta.env.VITE_API_URL}/api/compile`, payload)
      const data = response.data

      if (!data.success && data.status !== 'success') {
        throw new Error(data.error || 'Failed to compile blueprint layout.')
      }

      // Progress through the backend calculation stages beautifully
      const stageDurations = [0.4, 0.5, 0.4, 0.8, 0.5]
      for (let i = 0; i < 5; i++) {
        setCurrentStage(i)
        setCompilationStages((prev) => {
          const updated = [...prev]
          updated[i].status = 'running'
          return updated
        })

        await new Promise((resolve) => setTimeout(resolve, stageDurations[i] * 600))

        setCompilationStages((prev) => {
          const updated = [...prev]
          updated[i].status = 'complete'
          updated[i].duration = stageDurations[i]
          return updated
        })
      }

      // Final 3D rendering stage
      setCurrentStage(5)
      setCompilationStages((prev) => {
        const updated = [...prev]
        updated[5].status = 'running'
        return updated
      })

      await new Promise((resolve) => setTimeout(resolve, 800))

      setCompilationStages((prev) => {
        const updated = [...prev]
        updated[5].status = 'complete'
        updated[5].duration = 0.8
        return updated
      })

      // Set compiled building data for 3D viewer
      setBuildingData({
        floors: params.floors,
        width: params.plotWidth,
        depth: params.plotDepth,
        layout: data.layout,
        boundaries: data.boundaries,
        metadata: data.metadata,
        floors_data: data.floors,
        drawing_svg: data.drawing_svg,
      })


      // Map real metrics returned by the backend metrics engine
      const metrics = data.metrics || {}
      const totalArea = data.metadata.buildable_area_sqft * params.floors
      const usableArea = totalArea * 0.85

      setResults({
        totalArea: totalArea,
        usableArea: usableArea,
        plotCoverage: metrics.plot_coverage_pct || 0.0,
        fsi: metrics.fsi || 0.0,
        ventilationScore: metrics.cross_ventilation_score || 100.0,
        daylightScore: metrics.daylighting_score || 100.0,
        structuralCompliance: metrics.buildability_score || 100.0,
        estimatedCost: metrics.estimated_cost_inr ? `₹${metrics.estimated_cost_inr.toLocaleString('en-IN')}` : `₹0`,
        constructionTime: `${12 + params.floors * 2} months`,
      })

      // Store AI design explanation
      setExplanation(data.explanation || null)

      setCurrentStage(undefined)
      setShowResults(true)
    } catch (err) {
      console.error(err)
      const errorMsg = err.response?.data?.detail || err.message || 'Internal connection error.'

      // Determine where it failed to mark appropriate stage as error
      let failStageIdx = 0
      const errStr = errorMsg.toLowerCase()
      if (errStr.includes('privacy') || errStr.includes('topological')) {
        failStageIdx = 1 // Topological Validation
      } else if (errStr.includes('envelope') || errStr.includes('setback') || errStr.includes('geometric')) {
        failStageIdx = 2 // Geometric Constraints
      } else if (errStr.includes('optimization') || errStr.includes('solver') || errStr.includes('milp') || errStr.includes('infeasible')) {
        failStageIdx = 3 // MILP Optimization
      } else if (errStr.includes('ventilation') || errStr.includes('ots')) {
        failStageIdx = 4 // Ventilation Routing
      }

      setCompilationStages((prev) => {
        const updated = [...prev]
        for (let j = 0; j < updated.length; j++) {
          if (j < failStageIdx) {
            updated[j].status = 'complete'
            updated[j].duration = 0.5
          } else if (j === failStageIdx) {
            updated[j].status = 'error'
            updated[j].description = `Error: ${errorMsg}`
          } else {
            updated[j].status = 'pending'
          }
        }
        return updated
      })

      setCurrentStage(undefined)
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-background text-foreground">
      {/* Header */}
      <motion.header
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        className="border-b border-border sticky top-0 z-40 bg-background/95 backdrop-blur-sm"
      >
        <div className="max-w-7xl mx-auto px-6 py-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-light tracking-tight text-foreground">BuildForgeAI</h1>
              <p className="text-sm text-muted-foreground font-mono mt-1">
                Constraint-Driven Building Compiler
              </p>
            </div>
            <div className="text-right">
              <p className="text-xs text-muted-foreground font-mono">v1.0</p>
              <p className="text-xs text-muted-foreground font-mono">Dense Urban Real Estate</p>
            </div>
          </div>
        </div>
      </motion.header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-6 py-12">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-12">
          {/* Left Panel - Input/Results */}
          <div className="lg:col-span-1 space-y-8">
            <AnimatePresence mode="wait">
              {!showResults ? (
                <motion.div
                  key="input"
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -20 }}
                >
                  <BuildingInputForm onSubmit={handleCompilation} isLoading={isLoading} />
                </motion.div>
              ) : (
                <motion.div
                  key="results"
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -20 }}
                >
                  <ResultsPanel metrics={results} projectId={`AX-${Math.random().toString(36).substring(7).toUpperCase()}`} isVisible={true} explanation={explanation} />

                  <motion.button
                    whileHover={{ scale: 1.02 }}
                    whileTap={{ scale: 0.98 }}
                    onClick={() => {
                      setShowResults(false)
                      setBuildingData(null)
                      setResults(null)
                    }}
                    className="w-full mt-8 py-3 border border-border text-foreground hover:bg-card transition-colors text-sm font-mono uppercase tracking-wide cursor-pointer"
                  >
                    ← Start New Project
                  </motion.button>
                </motion.div>
              )}
            </AnimatePresence>

            {/* Status Panel */}
            <CompilationStatus
              stages={compilationStages}
              currentStage={currentStage}
              isVisible={isLoading || compilationStages.length > 0}
            />
          </div>

          {/* Right Panel - 3D/2D Viewer */}
          <div
            ref={viewerContainerRef}
            className={
              isFullscreen
                ? 'fixed inset-0 z-50 bg-[#07070a] p-4 flex flex-col space-y-3 h-screen w-screen overflow-hidden'
                : 'lg:col-span-2 space-y-4'
            }
          >
            {buildingData && (
              <div className="flex border border-border rounded-sm overflow-hidden bg-[#0d0e15] items-center justify-between">
                <button
                  onClick={() => setViewMode('3d')}
                  className={`flex-1 py-3 text-xs font-mono uppercase tracking-wider transition-colors cursor-pointer ${
                    viewMode === '3d'
                      ? 'bg-primary/10 text-primary font-bold border-r border-border'
                      : 'text-muted-foreground hover:bg-card/50 hover:text-foreground border-r border-border'
                  }`}
                >
                  3D WebGL Model
                </button>
                <button
                  onClick={() => setViewMode('2d')}
                  className={`flex-1 py-3 text-xs font-mono uppercase tracking-wider transition-colors cursor-pointer ${
                    viewMode === '2d'
                      ? 'bg-primary/10 text-primary font-bold border-r border-border'
                      : 'text-muted-foreground hover:bg-card/50 hover:text-foreground border-r border-border'
                  }`}
                >
                  2D CAD Drawing (Architectural SVG)
                </button>
                <button
                  onClick={toggleFullscreen}
                  className="px-3 py-3 text-muted-foreground hover:text-foreground hover:bg-card/50 transition-colors cursor-pointer border-l border-border"
                  title={isFullscreen ? "Exit Fullscreen (Esc)" : "Fullscreen Mode"}
                >
                  {isFullscreen ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
                </button>
              </div>
            )}

            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: 0.2 }}
              className={`border border-border rounded-sm overflow-hidden bg-card flex items-stretch ${
                isFullscreen ? 'flex-1 h-full w-full' : 'aspect-square lg:aspect-auto lg:h-[800px]'
              }`}
            >
              {viewMode === '3d' ? (
                <BuildingViewer3D
                  buildingData={buildingData}
                  isLoading={isLoading}
                  isFullscreen={isFullscreen}
                  onToggleFullscreen={toggleFullscreen}
                />
              ) : (
                <CADViewer2D
                  svgString={buildingData?.drawing_svg || ""}
                  isFullscreen={isFullscreen}
                  onToggleFullscreen={toggleFullscreen}
                />
              )}
            </motion.div>




            {/* Info Footer */}
            {!buildingData && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.4 }}
                className="mt-6 p-6 border border-border bg-card rounded-sm space-y-3"
              >
                <p className="text-sm text-foreground font-mono uppercase tracking-wide">
                  How It Works
                </p>
                <div className="text-xs text-muted-foreground space-y-2 font-mono">
                  <p>
                    1. Define your urban plot constraints (width, depth, floors, setbacks)
                  </p>
                  <p>
                    2. Describe your design intent in natural language
                  </p>
                  <p>
                    3. Our MILP solver optimizes layout for cross-ventilation and compliance
                  </p>
                  <p>
                    4. View the generated 3D blueprint and export for construction
                  </p>
                </div>
              </motion.div>
            )}
          </div>
        </div>
      </main>

      {/* Footer */}
      <motion.footer
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.6 }}
        className="border-t border-border mt-24 py-12"
      >
        <div className="max-w-7xl mx-auto px-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-12 text-xs text-muted-foreground font-mono mb-8">
            <div>
              <p className="uppercase tracking-widest mb-2">Tech Stack</p>
              <p>React Three Fiber · Vite · FastAPI · PuLP · Shapely</p>
            </div>
            <div>
              <p className="uppercase tracking-widest mb-2">Optimization</p>
              <p>MILP Solver · NetworkX · Computational Geometry · NSGA-II</p>
            </div>
            <div>
              <p className="uppercase tracking-widest mb-2">By</p>
              <p>Team Uncharted · Democratizing Structural Engineering</p>
            </div>
          </div>
          <div className="border-t border-border pt-8 text-center text-xs text-muted-foreground">
            <p>© 2026 Uncharted Building Compiler. All rights reserved.</p>
          </div>
        </div>
      </motion.footer>
    </div>
  )
}
