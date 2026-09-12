import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

// The width axis matters: this file, rather than `wght.css`, is what makes the
// condensed time column and headline figures possible from one family. Unused
// unicode subsets are never fetched, so the cost is a single woff2.
import '@fontsource-variable/archivo/wdth.css'
// The optical-size cut: a serif used from 28px to 96px wants different
// proportions at each end, and the axis is what supplies them.
import '@fontsource-variable/newsreader/opsz.css'
import './styles/index.css'

import { App } from './App'

const container = document.getElementById('root')
if (container === null) throw new Error('No #root element to mount into.')

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
