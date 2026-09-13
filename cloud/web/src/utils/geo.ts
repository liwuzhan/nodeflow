export function computeBounds(coordinates: number[][]): [[number, number], [number, number]] {
  let minLon = Infinity, minLat = Infinity, maxLon = -Infinity, maxLat = -Infinity
  for (const [lon, lat] of coordinates) {
    if (lon < minLon) minLon = lon
    if (lat < minLat) minLat = lat
    if (lon > maxLon) maxLon = lon
    if (lat > maxLat) maxLat = lat
  }
  return [[minLat, minLon], [maxLat, maxLon]]
}

export function centerOf(coordinates: number[][]): [number, number] {
  let sumLon = 0, sumLat = 0
  for (const [lon, lat] of coordinates) {
    sumLon += lon
    sumLat += lat
  }
  return [sumLat / coordinates.length, sumLon / coordinates.length]
}
