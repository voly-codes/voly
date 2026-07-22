const CARD_W = 220
const CARD_H = 132
const GAP_X = 76
const GAP_Y = 30
const PAD = 24

export function layoutAgentGraph(nodes = [], edges = []) {
  const ids = nodes.map((node, index) => String(node.id ?? `agent-${index}`))
  const depth = Object.fromEntries(ids.map(id => [id, 0]))
  const incoming = new Set(edges.map(edge => String(edge.to ?? '')))
  const roots = ids.filter(id => !incoming.has(id))

  if (roots.length) {
    for (let pass = 0; pass < ids.length; pass += 1) {
      let changed = false
      for (const edge of edges) {
        const from = String(edge.from ?? '')
        const to = String(edge.to ?? '')
        if (!(from in depth) || !(to in depth)) continue
        const next = Math.min(ids.length - 1, depth[from] + 1)
        if (next > depth[to]) { depth[to] = next; changed = true }
      }
      if (!changed) break
    }
  } else {
    ids.forEach((id, index) => { depth[id] = index })
  }

  const rows = {}
  const placed = nodes.map((node, index) => {
    const id = ids[index]
    const column = depth[id]
    const row = rows[column] ?? 0
    rows[column] = row + 1
    return { ...node, id, x: PAD + column * (CARD_W + GAP_X), y: PAD + row * (CARD_H + GAP_Y) }
  })
  const byId = Object.fromEntries(placed.map(node => [node.id, node]))
  const paths = edges.flatMap(edge => {
    const from = byId[String(edge.from ?? '')]
    const to = byId[String(edge.to ?? '')]
    if (!from || !to) return []
    const forward = to.x >= from.x
    const x1 = forward ? from.x + CARD_W : from.x
    const x2 = forward ? to.x : to.x + CARD_W
    const y1 = from.y + CARD_H / 2
    const y2 = to.y + CARD_H / 2
    const bend = Math.max(42, Math.abs(x2 - x1) * 0.45)
    const c1 = forward ? x1 + bend : x1 - bend
    const c2 = forward ? x2 - bend : x2 + bend
    return [{ ...edge, d: `M ${x1} ${y1} C ${c1} ${y1}, ${c2} ${y2}, ${x2} ${y2}` }]
  })
  const columns = Math.max(1, ...Object.values(depth).map(Number)) + 1
  const maxRows = Math.max(1, ...Object.values(rows).map(Number))
  return {
    nodes: placed,
    edges: paths,
    width: PAD * 2 + columns * CARD_W + (columns - 1) * GAP_X,
    height: PAD * 2 + maxRows * CARD_H + (maxRows - 1) * GAP_Y,
  }
}
