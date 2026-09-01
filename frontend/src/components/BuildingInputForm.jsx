import { useState } from 'react'
import { motion } from 'framer-motion'
import { Button } from '@/components/ui/button'

const defaultSetbacks = {
  front: 3,
  back: 2,
  left: 1.5,
  right: 1.5,
}

const presets = [
  {
    name: '30×40 2BHK Urban',
    width: 30,
    depth: 40,
    floors: 1,
    description: 'Design a modern 2BHK with living room, kitchen, dining, 2 bedrooms and 2 bathrooms',
    frontSetback: 5.0,
  },
  {
    name: '20×50 Rowhouse',
    width: 20,
    depth: 50,
    floors: 1,
    description: 'Design a linear rowhouse with front living, linear circulation spine, kitchen, dining and 2 bedrooms',
    frontSetback: 5.0,
  },
  {
    name: '50×35 Luxury Villa',
    width: 50,
    depth: 35,
    floors: 1,
    description: 'Design a spacious 3BHK villa with grand foyer, formal living wing, open kitchen/dining and master suites',
    frontSetback: 5.0,
  },
  {
    name: '25×30 1BHK + OTS',
    width: 25,
    depth: 30,
    floors: 1,
    description: 'Design a compact 1BHK with living room, kitchen with natural light, bedroom and bathroom with OTS lightwell',
    frontSetback: 5.0,
  },
  {
    name: '40×40 G+1 Duplex',
    width: 40,
    depth: 40,
    floors: 2,
    description: 'Design a G+1 duplex house with living, kitchen, bedrooms and internal staircase',
    frontSetback: 5.0,
  },
]

export function BuildingInputForm({ onSubmit, isLoading }) {
  const [plotWidth, setPlotWidth] = useState(30)
  const [plotDepth, setPlotDepth] = useState(40)
  const [floors, setFloors] = useState(1)
  const [description, setDescription] = useState(
    'Design a modern 2BHK with living room, kitchen, dining, 2 bedrooms and 2 bathrooms'
  )
  const [setbacks, setSetbacks] = useState(defaultSetbacks)
  const [showAdvanced, setShowAdvanced] = useState(false)

  const handleApplyPreset = (preset) => {
    setPlotWidth(preset.width)
    setPlotDepth(preset.depth)
    setFloors(preset.floors)
    setDescription(preset.description)
    setSetbacks((prev) => ({ ...prev, front: preset.frontSetback }))
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    onSubmit({
      plotWidth,
      plotDepth,
      floors,
      description,
      setbacks,
    })
  }

  return (
    <motion.form
      onSubmit={handleSubmit}
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
      className="space-y-6"
    >
      {/* Header */}
      <div className="border-b border-border pb-6">
        <h2 className="text-2xl font-light tracking-wide text-foreground mb-2">PLOT CONSTRAINTS</h2>
        <p className="text-sm text-muted-foreground font-mono">Define your urban plot or select a demo preset</p>
      </div>

      {/* Demo Presets Chips */}
      <div className="space-y-2">
        <label className="text-[11px] uppercase tracking-widest text-accent/80 font-mono font-semibold">
          ⚡ Quick Demo Presets
        </label>
        <div className="flex flex-wrap gap-2">
          {presets.map((preset) => (
            <button
              key={preset.name}
              type="button"
              onClick={() => handleApplyPreset(preset)}
              className="text-xs font-mono px-3 py-1.5 rounded-sm bg-card hover:bg-accent/20 border border-border hover:border-accent/50 text-foreground transition-all duration-150 cursor-pointer"
            >
              {preset.name}
            </button>
          ))}
        </div>
      </div>

      {/* Primary Parameters */}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="space-y-2">
          <label className="text-xs uppercase tracking-widest text-muted-foreground font-mono">
            Plot Width (ft)
          </label>
          <input
            type="number"
            value={plotWidth}
            onChange={(e) => setPlotWidth(parseFloat(e.target.value))}
            step="0.1"
            className="w-full bg-card border border-border px-4 py-3 text-foreground text-sm focus:outline-none focus:border-accent/50 transition-colors font-mono"
          />
          <p className="text-xs text-muted-foreground">Typical: 43.75 ft (dense urban)</p>
        </div>

        <div className="space-y-2">
          <label className="text-xs uppercase tracking-widest text-muted-foreground font-mono">
            Plot Depth (ft)
          </label>
          <input
            type="number"
            value={plotDepth}
            onChange={(e) => setPlotDepth(parseFloat(e.target.value))}
            step="0.1"
            className="w-full bg-card border border-border px-4 py-3 text-foreground text-sm focus:outline-none focus:border-accent/50 transition-colors font-mono"
          />
          <p className="text-xs text-muted-foreground">Typical: 41 ft (rental floors)</p>
        </div>

        <div className="space-y-2">
          <label className="text-xs uppercase tracking-widest text-muted-foreground font-mono">
            Number of Floors
          </label>
          <input
            type="number"
            value={floors}
            onChange={(e) => setFloors(Math.max(1, parseInt(e.target.value)))}
            min="1"
            max="10"
            className="w-full bg-card border border-border px-4 py-3 text-foreground text-sm focus:outline-none focus:border-accent/50 transition-colors font-mono"
          />
          <p className="text-xs text-muted-foreground">G+2 standard: 3 floors</p>
        </div>

        <div className="space-y-2">
          <label className="text-xs uppercase tracking-widest text-muted-foreground font-mono">
            Building Height (ft)
          </label>
          <input
            type="number"
            value={Math.round(floors * 10)}
            disabled
            className="w-full bg-muted border border-border px-4 py-3 text-muted-foreground text-sm cursor-not-allowed font-mono"
          />
          <p className="text-xs text-muted-foreground">Auto-calculated (~10ft per floor)</p>
        </div>
      </div>

      {/* Description */}
      <div className="space-y-2">
        <label className="text-xs uppercase tracking-widest text-muted-foreground font-mono">
          Design Brief
        </label>
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={4}
          className="w-full bg-card border border-border px-4 py-3 text-foreground text-sm focus:outline-none focus:border-accent/50 transition-colors font-mono resize-none"
          placeholder="Describe your building requirements, room layout preferences, and constraints..."
        />
        <p className="text-xs text-muted-foreground">
          Parsed by intent engine for topological validation
        </p>
      </div>

      {/* Advanced Setbacks */}
      <div className="border-t border-border pt-6">
        <button
          type="button"
          onClick={() => setShowAdvanced(!showAdvanced)}
          className="text-xs uppercase tracking-widest text-muted-foreground font-mono hover:text-foreground transition-colors flex items-center gap-2"
        >
          <span>{showAdvanced ? '−' : '+'}</span>
          Municipal Setbacks (Advanced)
        </button>

        {showAdvanced && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-6 pt-6 border-t border-border"
          >
            {Object.keys(setbacks).map((side) => (
              <div key={side} className="space-y-2">
                <label className="text-xs uppercase tracking-widest text-muted-foreground font-mono">
                  {side} (ft)
                </label>
                <input
                  type="number"
                  value={setbacks[side]}
                  onChange={(e) =>
                    setSetbacks({
                      ...setbacks,
                      [side]: parseFloat(e.target.value),
                    })
                  }
                  step="0.1"
                  className="w-full bg-card border border-border px-3 py-2 text-foreground text-sm focus:outline-none focus:border-accent/50 transition-colors font-mono"
                />
              </div>
            ))}
          </motion.div>
        )}
      </div>

      {/* Submit */}
      <div className="flex gap-4 pt-6 border-t border-border">
        <Button
          type="submit"
          disabled={isLoading}
          className="flex-1 bg-foreground text-background hover:bg-foreground/90 disabled:opacity-50 disabled:cursor-not-allowed font-mono text-sm tracking-wide uppercase h-10"
        >
          {isLoading ? (
            <div className="flex items-center gap-2">
              <div className="w-4 h-4 border-2 border-background/30 border-t-background rounded-full animate-spin" />
              Compiling...
            </div>
          ) : (
            'Generate Blueprint'
          )}
        </Button>
      </div>

      {/* Info Footer */}
      <div className="bg-card border border-border p-4 rounded-sm space-y-2">
        <p className="text-xs uppercase tracking-widest text-muted-foreground font-mono">
          COMPILATION PIPELINE
        </p>
        <div className="text-xs text-muted-foreground space-y-1">
          <div className="flex items-center gap-2">
            <span className="w-1 h-1 bg-accent rounded-full" />
            <span>Intent Parsing → Topological Validation → Geometric Constraints</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-1 h-1 bg-accent rounded-full" />
            <span>MILP Optimization → Ventilation Routing → 3D Rendering</span>
          </div>
        </div>
      </div>
    </motion.form>
  )
}
